#!/usr/bin/env python3
"""
alienware_rgb.py — AlienWare x17 R1 RGB Lighting Controller for Linux

Controls keyboard, logo, lightbar, and other RGB zones via OpenRGB.

Usage (CLI):
    python alienware_rgb.py --zone all --color FF0000
    python alienware_rgb.py --zone keyboard --effect rainbow
    python alienware_rgb.py --zone logo --color "#00FF00"
    python alienware_rgb.py --list-zones
    python alienware_rgb.py           # interactive menu

Install:
    pip install openrgb-python
    # Install & launch OpenRGB with SDK server enabled:
    #   openrgb --server   OR enable "SDK Server" in OpenRGB GUI (Edit > Settings)
    # Default SDK port: 6742
"""

import argparse
import sys
import re
import time
import math
import signal
import threading
from typing import Optional, Tuple, List, Dict

# ─── dependency check ────────────────────────────────────────────────────────

try:
    from openrgb import OpenRGBClient
    from openrgb.utils import RGBColor, ModeFlags
    OPENRGB_AVAILABLE = True
except ImportError:
    OPENRGB_AVAILABLE = False

# ─── constants ───────────────────────────────────────────────────────────────

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 6742

# Zone keyword → substrings that match OpenRGB zone/device names (case-insensitive)
ZONE_KEYWORDS: Dict[str, List[str]] = {
    "keyboard":  ["keyboard", "kbd"],
    "logo":      ["logo", "alien", "lid"],
    "lightbar":  ["lightbar", "light bar", "bar", "chassis"],
    "power":     ["power"],
    "touchpad":  ["touchpad", "touch pad"],
}

NAMED_COLORS: Dict[str, str] = {
    "red":     "FF0000",
    "green":   "00FF00",
    "blue":    "0000FF",
    "white":   "FFFFFF",
    "off":     "000000",
    "black":   "000000",
    "cyan":    "00FFFF",
    "magenta": "FF00FF",
    "yellow":  "FFFF00",
    "orange":  "FF6600",
    "purple":  "8000FF",
    "pink":    "FF0080",
    "teal":    "008080",
}

EFFECTS = ["static", "rainbow", "breathing", "off"]

# ─── color utilities ─────────────────────────────────────────────────────────

def parse_color(value: str) -> Tuple[int, int, int]:
    """Parse a color from a hex string, named color, or 'r,g,b' tuple."""
    v = value.strip().lstrip("#").lower()

    if v in NAMED_COLORS:
        v = NAMED_COLORS[v]

    # Hex: RRGGBB or RGB shorthand
    m6 = re.fullmatch(r"([0-9a-f]{6})", v)
    if m6:
        h = m6.group(1)
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)

    m3 = re.fullmatch(r"([0-9a-f]{3})", v)
    if m3:
        h = m3.group(1)
        return int(h[0]*2, 16), int(h[1]*2, 16), int(h[2]*2, 16)

    # r,g,b
    m = re.fullmatch(r"(\d{1,3})[,\s]+(\d{1,3})[,\s]+(\d{1,3})", v)
    if m:
        r, g, b = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if all(0 <= x <= 255 for x in (r, g, b)):
            return r, g, b

    raise ValueError(
        f"Unrecognized color '{value}'. "
        "Use hex (#FF0000), shorthand (F00), rgb tuple (255,0,0), or a name like 'red'."
    )


def hsv_to_rgb(h: float, s: float, v: float) -> Tuple[int, int, int]:
    """h in [0,360), s and v in [0,1]. Returns (r,g,b) 0-255."""
    h = h % 360
    c = v * s
    x = c * (1 - abs((h / 60) % 2 - 1))
    m = v - c
    if h < 60:   r, g, b = c, x, 0
    elif h < 120: r, g, b = x, c, 0
    elif h < 180: r, g, b = 0, c, x
    elif h < 240: r, g, b = 0, x, c
    elif h < 300: r, g, b = x, 0, c
    else:         r, g, b = c, 0, x
    return int((r + m) * 255), int((g + m) * 255), int((b + m) * 255)

# ─── OpenRGB helpers ──────────────────────────────────────────────────────────

def connect(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> "OpenRGBClient":
    if not OPENRGB_AVAILABLE:
        die(
            "openrgb-python is not installed.\n"
            "  pip install openrgb-python\n\n"
            "You also need OpenRGB running with SDK server enabled:\n"
            "  openrgb --server\n"
            "  (or enable it in the GUI under Edit > Settings > SDK Server)"
        )
    try:
        client = OpenRGBClient(host, port)
        return client
    except ConnectionRefusedError:
        die(
            f"Could not connect to OpenRGB SDK at {host}:{port}.\n"
            "Make sure OpenRGB is running with '--server' or SDK Server enabled in settings."
        )
    except Exception as e:
        die(f"Connection error: {e}")


def list_all_zones(client: "OpenRGBClient") -> List[dict]:
    """Return a flat list of {device_idx, device_name, zone_idx, zone_name, zone_obj} dicts."""
    zones = []
    for di, dev in enumerate(client.devices):
        for zi, zone in enumerate(dev.zones):
            zones.append({
                "device_idx": di,
                "device_name": dev.name,
                "zone_idx": zi,
                "zone_name": zone.name,
                "zone": zone,
                "device": dev,
            })
    return zones


def find_zones(client: "OpenRGBClient", zone_key: str) -> List[dict]:
    """
    Match zone_key against known keywords, or match directly against zone/device names.
    Returns a list of matching zone dicts.  'all' returns everything.
    """
    all_zones = list_all_zones(client)

    if zone_key.lower() == "all":
        return all_zones

    keywords = ZONE_KEYWORDS.get(zone_key.lower())
    if keywords is None:
        # Treat as a raw substring match
        keywords = [zone_key.lower()]

    matched = []
    for z in all_zones:
        combined = (z["device_name"] + " " + z["zone_name"]).lower()
        if any(kw in combined for kw in keywords):
            matched.append(z)

    return matched

# ─── lighting actions ─────────────────────────────────────────────────────────

def set_static_color(zones: List[dict], r: int, g: int, b: int):
    """Set all LEDs in the given zones to a single static color."""
    color = RGBColor(r, g, b)
    devices_seen = set()
    for z in zones:
        dev = z["device"]
        # Try to switch to a direct/static mode first
        _try_set_static_mode(dev, devices_seen)
        z["zone"].set_color(color)
    print(f"  Set {len(zones)} zone(s) to #{r:02X}{g:02X}{b:02X}")


def _try_set_static_mode(dev, devices_seen: set):
    """Switch a device to its 'Direct' or 'Static' mode, once per device."""
    if id(dev) in devices_seen:
        return
    devices_seen.add(id(dev))
    for i, mode in enumerate(dev.modes):
        if mode.name.lower() in ("direct", "static", "color"):
            try:
                dev.set_mode(i)
            except Exception:
                pass
            return


def set_native_effect(zones: List[dict], effect_name: str) -> bool:
    """
    Try to enable a hardware effect matching effect_name on each device.
    Returns True if at least one device supports it natively.
    """
    effect_lower = effect_name.lower()
    effect_aliases = {
        "rainbow": ("rainbow", "rainbow wave", "color cycle", "spectrum cycle",
                    "spectrum", "cycle", "wave"),
        "breathing": ("breathing", "breath", "pulse", "sinusoidal"),
    }
    candidates = effect_aliases.get(effect_lower, (effect_lower,))

    success = False
    devices_seen = set()
    for z in zones:
        dev = z["device"]
        if id(dev) in devices_seen:
            continue
        devices_seen.add(id(dev))
        for i, mode in enumerate(dev.modes):
            if mode.name.lower() in candidates:
                try:
                    dev.set_mode(i)
                    success = True
                except Exception:
                    pass
                break
    return success


_rainbow_stop = threading.Event()

def set_rainbow_software(zones: List[dict], speed: float = 1.0):
    """
    Software rainbow cycle — rotates hue across all zones continuously.
    Press Ctrl-C to stop.
    """
    print("  Running software rainbow (Ctrl-C to stop)...")
    _rainbow_stop.clear()

    # Pre-set to direct mode
    devices_seen = set()
    for z in zones:
        _try_set_static_mode(z["device"], devices_seen)

    hue = 0.0
    try:
        while not _rainbow_stop.is_set():
            for idx, z in enumerate(zones):
                # Stagger hue per zone for a wave effect
                zone_hue = (hue + idx * (360 / max(len(zones), 1))) % 360
                r, g, b = hsv_to_rgb(zone_hue, 1.0, 1.0)
                try:
                    z["zone"].set_color(RGBColor(r, g, b))
                except Exception:
                    pass
            hue = (hue + speed * 2) % 360
            time.sleep(0.05)
    except KeyboardInterrupt:
        pass
    print("\n  Rainbow stopped.")


def set_breathing_software(zones: List[dict], r: int, g: int, b: int, speed: float = 1.0):
    """Software breathing effect for a given color."""
    print("  Running software breathing (Ctrl-C to stop)...")
    _rainbow_stop.clear()

    devices_seen = set()
    for z in zones:
        _try_set_static_mode(z["device"], devices_seen)

    t = 0.0
    try:
        while not _rainbow_stop.is_set():
            brightness = (math.sin(t) + 1) / 2   # 0..1
            cr = int(r * brightness)
            cg = int(g * brightness)
            cb = int(b * brightness)
            color = RGBColor(cr, cg, cb)
            for z in zones:
                try:
                    z["zone"].set_color(color)
                except Exception:
                    pass
            t += 0.05 * speed
            time.sleep(0.05)
    except KeyboardInterrupt:
        pass
    print("\n  Breathing stopped.")

# ─── zone display ─────────────────────────────────────────────────────────────

def print_zones(client: "OpenRGBClient"):
    zones = list_all_zones(client)
    print(f"\n{'#':<4} {'Device':<35} {'Zone':<25} LEDs")
    print("─" * 72)
    for i, z in enumerate(zones):
        led_count = len(z["zone"].leds) if hasattr(z["zone"], "leds") else "?"
        print(f"{i:<4} {z['device_name']:<35} {z['zone_name']:<25} {led_count}")
    print()

# ─── interactive menu ─────────────────────────────────────────────────────────

def interactive(client: "OpenRGBClient"):
    print("\n╔══════════════════════════════════════╗")
    print("║  AlienWare RGB Controller             ║")
    print("╚══════════════════════════════════════╝\n")

    # Zone selection
    all_zones = list_all_zones(client)
    print("Available zones:")
    print(f"  {'0':<4} ALL zones")
    for i, z in enumerate(all_zones, 1):
        print(f"  {i:<4} {z['device_name']} › {z['zone_name']}")

    zone_input = input("\nSelect zone(s) [0=all, number, or name like 'keyboard']: ").strip()

    if zone_input == "0" or zone_input.lower() == "all":
        chosen_zones = all_zones
        zone_label = "ALL"
    elif zone_input.isdigit():
        idx = int(zone_input) - 1
        if 0 <= idx < len(all_zones):
            chosen_zones = [all_zones[idx]]
            z = all_zones[idx]
            zone_label = f"{z['device_name']} › {z['zone_name']}"
        else:
            print("Invalid selection."); return
    else:
        chosen_zones = find_zones(client, zone_input)
        zone_label = zone_input
        if not chosen_zones:
            print(f"No zones matched '{zone_input}'."); return

    print(f"\n  → Targeting: {zone_label} ({len(chosen_zones)} zone(s))\n")

    # Effect selection
    print("Effects:")
    print("  1  Static color (enter a hex or name)")
    print("  2  Rainbow (hardware if supported, else software)")
    print("  3  Breathing (software)")
    print("  4  Off")

    choice = input("\nChoose effect [1-4]: ").strip()

    if choice == "1":
        color_input = input("  Color (#RRGGBB, name, or r,g,b): ").strip()
        try:
            r, g, b = parse_color(color_input)
        except ValueError as e:
            print(f"  Error: {e}"); return
        set_static_color(chosen_zones, r, g, b)

    elif choice == "2":
        if not set_native_effect(chosen_zones, "rainbow"):
            set_rainbow_software(chosen_zones)
        else:
            print("  Hardware rainbow mode activated.")

    elif choice == "3":
        color_input = input("  Base color (#RRGGBB or name) [default: white]: ").strip() or "white"
        try:
            r, g, b = parse_color(color_input)
        except ValueError as e:
            print(f"  Error: {e}"); return
        if not set_native_effect(chosen_zones, "breathing"):
            set_breathing_software(chosen_zones, r, g, b)
        else:
            print("  Hardware breathing mode activated.")

    elif choice == "4":
        set_static_color(chosen_zones, 0, 0, 0)

    else:
        print("  Unknown choice.")

# ─── CLI ─────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="alienware_rgb",
        description="Control AlienWare x17 R1 RGB zones from the command line.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  %(prog)s --zone all --color FF0000
  %(prog)s --zone keyboard --color "#00BFFF"
  %(prog)s --zone logo --color red
  %(prog)s --zone lightbar --effect rainbow
  %(prog)s --zone keyboard --effect breathing --color 8000FF
  %(prog)s --zone all --effect off
  %(prog)s --list-zones
  %(prog)s                                    # interactive menu

zones:
  keyboard  logo  lightbar  power  touchpad  all
  (or any substring of a zone/device name from --list-zones)

colors:
  hex     #FF0000  or  FF0000
  name    red green blue white cyan magenta yellow orange purple pink off
  tuple   255,0,0

effects:
  static    apply a solid color (requires --color)
  rainbow   cycle through all hues (hardware if supported, else software)
  breathing fade in/out (hardware if supported, else software; optionally --color)
  off       turn lights off

OpenRGB must be running:
  openrgb --server          # CLI, headless
  (or enable SDK Server in OpenRGB GUI → Edit → Settings)
""",
    )
    p.add_argument("--zone", "-z", default=None,
                   help="Zone to control: keyboard, logo, lightbar, power, touchpad, all, or a custom substring")
    p.add_argument("--color", "-c", default=None,
                   help="Color: hex (#FF0000), name (red), or rgb tuple (255,0,0)")
    p.add_argument("--effect", "-e", default=None,
                   choices=EFFECTS,
                   help="Lighting effect: static, rainbow, breathing, off")
    p.add_argument("--list-zones", "-l", action="store_true",
                   help="List all detected RGB zones and exit")
    p.add_argument("--host", default=DEFAULT_HOST,
                   help=f"OpenRGB SDK host (default: {DEFAULT_HOST})")
    p.add_argument("--port", "-p", type=int, default=DEFAULT_PORT,
                   help=f"OpenRGB SDK port (default: {DEFAULT_PORT})")
    return p


def die(msg: str):
    print(f"\nError: {msg}\n", file=sys.stderr)
    sys.exit(1)


def main():
    parser = build_parser()
    args = parser.parse_args()

    client = connect(args.host, args.port)

    # ── list zones and exit ──
    if args.list_zones:
        print_zones(client)
        return

    # ── no args → interactive ──
    if args.zone is None and args.effect is None and args.color is None:
        interactive(client)
        return

    # ── validate CLI args ──
    if args.zone is None:
        die("--zone is required when using --effect or --color. See --help.")

    if args.effect is None and args.color is None:
        die("Specify --effect and/or --color. See --help.")

    effect = args.effect or "static"
    if effect == "static" and args.color is None:
        die("--color is required for the 'static' effect.")

    # ── resolve zones ──
    zones = find_zones(client, args.zone)
    if not zones:
        die(
            f"No zones matched '{args.zone}'.\n"
            "Run with --list-zones to see what's available."
        )
    print(f"  Zones matched: {len(zones)}")
    for z in zones:
        print(f"    • {z['device_name']} › {z['zone_name']}")

    # ── parse color if provided ──
    color_rgb = None
    if args.color:
        try:
            color_rgb = parse_color(args.color)
        except ValueError as e:
            die(str(e))

    # ── apply effect ──
    if effect == "off":
        set_static_color(zones, 0, 0, 0)

    elif effect == "static":
        r, g, b = color_rgb
        set_static_color(zones, r, g, b)

    elif effect == "rainbow":
        if not set_native_effect(zones, "rainbow"):
            set_rainbow_software(zones)
        else:
            print("  Hardware rainbow mode activated.")

    elif effect == "breathing":
        r, g, b = color_rgb or (255, 255, 255)
        if not set_native_effect(zones, "breathing"):
            set_breathing_software(zones, r, g, b)
        else:
            print("  Hardware breathing mode activated.")


if __name__ == "__main__":
    main()
