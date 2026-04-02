#!/usr/bin/env python3
"""
gpu_monitor.py — GPU Load → RGB Lighting Monitor

Continuously reads GPU utilization and maps it to a color gradient:
  0%  → cool blue
  50% → cyan / green
  90%+ → orange / red

Usage:
    python gpu_monitor.py
    python gpu_monitor.py --zone all --interval 2
    python gpu_monitor.py --zone keyboard --smooth 5
    python gpu_monitor.py --gpu amd
"""

import sys
import time
import argparse
import subprocess
import collections
import os
from pathlib import Path

# Import shared helpers from alienware_rgb.py in the same directory
sys.path.insert(0, str(Path(__file__).parent))
from alienware_rgb import connect, find_zones, _try_set_static_mode, DEFAULT_HOST, DEFAULT_PORT

try:
    from openrgb.utils import RGBColor
    OPENRGB_AVAILABLE = True
except ImportError:
    OPENRGB_AVAILABLE = False

# ─── color gradient ───────────────────────────────────────────────────────────
#
# Maps GPU load (0–100) to a hue sweep:
#   0%   → 220° (deep blue)
#   100% → 0°   (red)
#
# Saturation and brightness stay high throughout so the color is vivid.
# The sweep goes blue → cyan → green → yellow → orange → red.

def load_to_rgb(pct: float) -> tuple:
    """Map a 0–100 load percentage to an (r, g, b) tuple."""
    pct = max(0.0, min(100.0, pct))

    # Hue: 220° (blue) down to 0° (red) as load increases
    hue = 220.0 * (1.0 - pct / 100.0)

    # Ramp up saturation slightly at high load for extra urgency
    saturation = 0.85 + 0.15 * (pct / 100.0)

    # Brightness: full at all times
    value = 1.0

    return hsv_to_rgb(hue, saturation, value)


def hsv_to_rgb(h: float, s: float, v: float) -> tuple:
    """Convert HSV (h in [0,360), s/v in [0,1]) to (r,g,b) 0–255."""
    h = h % 360
    c = v * s
    x = c * (1 - abs((h / 60) % 2 - 1))
    m = v - c
    if   h < 60:  r, g, b = c, x, 0
    elif h < 120: r, g, b = x, c, 0
    elif h < 180: r, g, b = 0, c, x
    elif h < 240: r, g, b = 0, x, c
    elif h < 300: r, g, b = x, 0, c
    else:         r, g, b = c, 0, x
    return int((r + m) * 255), int((g + m) * 255), int((b + m) * 255)


def rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{r:02X}{g:02X}{b:02X}"


# ─── terminal display ──────────────────────────────────────────────────────────

BAR_WIDTH = 40

def draw_bar(pct: float, r: int, g: int, b: int):
    """Print an ANSI-colored load bar to stdout (overwrites the current line)."""
    filled  = int(BAR_WIDTH * pct / 100)
    empty   = BAR_WIDTH - filled
    bar     = "█" * filled + "░" * empty
    hex_col = rgb_to_hex(r, g, b)

    # ANSI 24-bit foreground color
    color_esc  = f"\033[38;2;{r};{g};{b}m"
    reset      = "\033[0m"
    bold       = "\033[1m"

    print(
        f"\r  GPU {bold}{pct:5.1f}%{reset}  "
        f"{color_esc}{bar}{reset}  "
        f"{color_esc}{bold}{hex_col}{reset}   ",
        end="",
        flush=True,
    )


# ─── GPU readers ──────────────────────────────────────────────────────────────

def read_nvidia() -> float:
    """Query NVIDIA GPU utilization via nvidia-smi."""
    try:
        result = subprocess.run(
            ["nvidia-smi",
             "--query-gpu=utilization.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            # May return multiple lines for multi-GPU; average them
            values = [float(v.strip()) for v in result.stdout.strip().splitlines() if v.strip()]
            if values:
                return sum(values) / len(values)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    raise RuntimeError("nvidia-smi not available or failed.")


def read_amd() -> float:
    """
    Read AMD GPU utilization from sysfs.
    Tries all card* entries and returns the highest load found.
    """
    candidates = sorted(Path("/sys/class/drm").glob("card*/device/gpu_busy_percent"))
    if not candidates:
        # Older kernels use a different path
        candidates = sorted(Path("/sys/kernel/debug/dri").glob("*/amdgpu_pm_info"))

    for path in candidates:
        try:
            return float(path.read_text().strip())
        except (OSError, ValueError):
            continue
    raise RuntimeError("AMD sysfs GPU stats not found.")


def read_intel() -> float:
    """
    Read Intel integrated GPU utilization via intel_gpu_top (requires root)
    or fall back to the i915 sysfs engine utilization (kernel 5.17+).
    """
    # Try sysfs engine utilization (newer kernels)
    busy_files  = sorted(Path("/sys/class/drm").glob("card*/gt/gt0/engines/*/busy"))
    total_files = sorted(Path("/sys/class/drm").glob("card*/gt/gt0/engines/*/total"))

    if busy_files and total_files:
        try:
            b1 = [int(f.read_text()) for f in busy_files]
            time.sleep(0.1)
            b2 = [int(f.read_text()) for f in busy_files]
            t1 = [int(f.read_text()) for f in total_files]
            time.sleep(0.1)
            t2 = [int(f.read_text()) for f in total_files]
            usages = []
            for db, dt in zip(
                [b - a for a, b in zip(b1, b2)],
                [b - a for a, b in zip(t1, t2)]
            ):
                if dt > 0:
                    usages.append(100.0 * db / dt)
            if usages:
                return max(usages)
        except (OSError, ValueError):
            pass

    raise RuntimeError(
        "Intel GPU sysfs stats not available.\n"
        "  Requires kernel 5.17+ or run intel_gpu_top manually."
    )


def auto_detect_gpu() -> str:
    """Return 'nvidia', 'amd', or raise if nothing found."""
    # Try nvidia-smi first
    try:
        r = subprocess.run(["nvidia-smi"], capture_output=True, timeout=3)
        if r.returncode == 0:
            return "nvidia"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Check for AMD sysfs
    if list(Path("/sys/class/drm").glob("card*/device/gpu_busy_percent")):
        return "amd"

    # Check for Intel i915
    if list(Path("/sys/class/drm").glob("card*/gt/gt0/engines")):
        return "intel"

    raise RuntimeError(
        "Could not auto-detect GPU type.\n"
        "Use --gpu nvidia|amd|intel to specify manually."
    )


GPU_READERS = {
    "nvidia": read_nvidia,
    "amd":    read_amd,
    "intel":  read_intel,
}


# ─── main loop ────────────────────────────────────────────────────────────────

def monitor(zones, read_gpu, interval: float, smooth: int):
    """Main polling loop — reads GPU load and updates lighting."""
    history = collections.deque(maxlen=smooth)
    devices_seen = set()

    # Pre-switch all devices to direct/static mode once
    for z in zones:
        _try_set_static_mode(z["device"], devices_seen)

    print(f"\n  Monitoring GPU — Ctrl-C to stop\n")

    try:
        while True:
            try:
                raw = read_gpu()
            except RuntimeError as e:
                print(f"\n  GPU read error: {e}")
                time.sleep(interval)
                continue

            history.append(raw)
            smoothed = sum(history) / len(history)

            r, g, b = load_to_rgb(smoothed)
            color   = RGBColor(r, g, b)

            for z in zones:
                try:
                    z["zone"].set_color(color)
                except Exception:
                    pass

            draw_bar(smoothed, r, g, b)
            time.sleep(interval)

    except KeyboardInterrupt:
        print("\n\n  Monitor stopped.")
        # Fade out to off
        print("  Turning lights off...")
        for z in zones:
            try:
                z["zone"].set_color(RGBColor(0, 0, 0))
            except Exception:
                pass


# ─── CLI ─────────────────────────────────────────────────────────────────────

def build_parser():
    p = argparse.ArgumentParser(
        prog="gpu_monitor",
        description="Map GPU utilization to RGB lighting in real time.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
color scale:
    0%   → deep blue  (#0066FF)
    25%  → cyan       (#00FFDD)
    50%  → green      (#00FF44)
    75%  → yellow     (#AAFF00)
    90%+ → orange/red (#FF4400 → #FF0000)

examples:
  %(prog)s
  %(prog)s --zone all --interval 1
  %(prog)s --zone keyboard --gpu nvidia --smooth 5
  %(prog)s --zone lightbar --interval 0.5
""",
    )
    p.add_argument("--zone", "-z", default="all",
                   help="Zone to control (default: all)")
    p.add_argument("--gpu", "-g", default=None,
                   choices=["nvidia", "amd", "intel"],
                   help="GPU type (default: auto-detect)")
    p.add_argument("--interval", "-i", type=float, default=2.0,
                   help="Poll interval in seconds (default: 2.0)")
    p.add_argument("--smooth", "-s", type=int, default=3,
                   help="Number of readings to average for smoothing (default: 3)")
    p.add_argument("--host", default=DEFAULT_HOST,
                   help=f"OpenRGB SDK host (default: {DEFAULT_HOST})")
    p.add_argument("--port", "-p", type=int, default=DEFAULT_PORT,
                   help=f"OpenRGB SDK port (default: {DEFAULT_PORT})")
    return p


def main():
    if not OPENRGB_AVAILABLE:
        print("Error: openrgb-python is not installed.  pip install openrgb-python")
        sys.exit(1)

    args = build_parser().parse_args()

    # Detect GPU
    gpu_type = args.gpu
    if gpu_type is None:
        print("  Auto-detecting GPU...", end=" ", flush=True)
        try:
            gpu_type = auto_detect_gpu()
            print(f"{gpu_type.upper()} found.")
        except RuntimeError as e:
            print(f"\n  Error: {e}")
            sys.exit(1)
    else:
        print(f"  Using GPU type: {gpu_type.upper()}")

    read_gpu = GPU_READERS[gpu_type]

    # Test read
    print("  Testing GPU read...", end=" ", flush=True)
    try:
        val = read_gpu()
        print(f"OK ({val:.1f}%)")
    except RuntimeError as e:
        print(f"\n  Error: {e}")
        sys.exit(1)

    # Connect to OpenRGB
    print(f"  Connecting to OpenRGB at {args.host}:{args.port}...", end=" ", flush=True)
    client = connect(args.host, args.port)
    print("connected.")

    # Resolve zones
    zones = find_zones(client, args.zone)
    if not zones:
        print(f"\n  Error: No zones matched '{args.zone}'. Run alienware_rgb.py --list-zones.")
        sys.exit(1)
    print(f"  Zones: {', '.join(f\"{z['device_name']} › {z['zone_name']}\" for z in zones)}")
    print(f"  Interval: {args.interval}s   Smoothing: {args.smooth} samples")

    monitor(zones, read_gpu, args.interval, args.smooth)


if __name__ == "__main__":
    main()
