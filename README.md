# alienware-rgb

A Linux (and Windows) Python CLI for controlling RGB lighting zones on the **AlienWare x17 R1** — keyboard, alien logo, lightbar, power button, touchpad, and more. May work on other Alienware devices, but designed specifically for the x17 laptop.

Supports static colors, rainbow cycling, and breathing effects. Can be run interactively or fully from the command line for scripting.

---

## Requirements

- Python 3.8+
- [`openrgb-python`](https://pypi.org/project/openrgb-python/) — `pip install openrgb-python`
- [OpenRGB](https://openrgb.org/) running with SDK Server enabled

---

## Install

### Fedora
```bash
sudo dnf install openrgb

# Download udev rules (not bundled in the Fedora package)
sudo curl -L "https://gitlab.com/CalcProgrammer1/OpenRGB/-/raw/master/qt/60-openrgb.rules" \
  -o /etc/udev/rules.d/60-openrgb.rules
sudo udevadm control --reload-rules && sudo udevadm trigger
# Log out and back in
```

### Ubuntu / Debian
```bash
sudo apt install openrgb
sudo cp /usr/share/openrgb/udev/60-openrgb.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger
# Log out and back in
```

### Python dependency + command setup (Linux)
```bash
bash setup.sh
```
This installs `openrgb-python`, makes the script executable, and symlinks it as `alienware-rgb` in `~/.local/bin`.

If `~/.local/bin` isn't in your PATH, add this to `~/.bashrc` or `~/.zshrc`:
```bash
export PATH="$HOME/.local/bin:$PATH"
```

### Windows
```powershell
pip install openrgb-python
# Download OpenRGB installer from https://openrgb.org/
```

---

## Start OpenRGB SDK Server

The script communicates with OpenRGB over its SDK server (port 6742). Keep it running in the background whenever you use the script.

```bash
openrgb --server
```

Or enable it in the GUI: **Edit → Settings → SDK Server → Start Server**

Flatpak:
```bash
flatpak run org.openrgb.OpenRGB --server
```

---

## Usage

### Interactive mode
```bash
alienware-rgb
```
Presents a menu to pick a zone and effect — no arguments needed.

### List detected zones
```bash
alienware-rgb --list-zones
```

### Static color
```bash
alienware-rgb --zone all --color FF0000
alienware-rgb --zone keyboard --color "#00BFFF"
alienware-rgb --zone logo --color red
alienware-rgb --zone lightbar --color "255,128,0"
```

### Effects
```bash
alienware-rgb --zone all --effect rainbow
alienware-rgb --zone keyboard --effect breathing --color 8000FF
alienware-rgb --zone all --effect off
```

### Short flags
```bash
alienware-rgb -z keyboard -c FF0000
alienware-rgb -z all -e rainbow
```

### Remote OpenRGB instance
```bash
alienware-rgb --host 192.168.1.10 --port 6742 --zone all --color 00FF00
```

---

## Zones

| Keyword    | Matches (case-insensitive substring)      |
|------------|-------------------------------------------|
| `keyboard` | keyboard, kbd                             |
| `logo`     | logo, alien, lid                          |
| `lightbar` | lightbar, light bar, bar, chassis         |
| `power`    | power                                     |
| `touchpad` | touchpad, touch pad                       |
| `all`      | every zone on every detected device       |

You can also pass any custom substring (e.g. `--zone "Zone 3"`) to match directly against zone/device names shown in `--list-zones`.

---

## Colors

| Format      | Example          |
|-------------|------------------|
| Hex         | `FF0000` or `#FF0000` |
| Hex short   | `F00`            |
| RGB tuple   | `255,0,0`        |
| Named       | `red`, `green`, `blue`, `white`, `cyan`, `magenta`, `yellow`, `orange`, `purple`, `pink`, `teal`, `off` |

---

## Effects

| Effect      | Description                                                                 |
|-------------|-----------------------------------------------------------------------------|
| `static`    | Solid color (requires `--color`)                                            |
| `rainbow`   | Cycles through all hues. Uses hardware mode if supported, else software.    |
| `breathing` | Fades in/out. Uses hardware mode if supported, else software. Optional `--color`. |
| `off`       | Turns all lights off (alias for `--color 000000`)                          |

Software rainbow and breathing effects run until you press **Ctrl-C**.

---

## GPU Load Monitor

`gpu_monitor.py` runs continuously and maps GPU utilization to a live color gradient on any zone:

| Load | Color |
|------|-------|
| 0%   | Deep blue `#0066FF` |
| 25%  | Cyan `#00FFDD` |
| 50%  | Green `#00FF44` |
| 75%  | Yellow `#AAFF00` |
| 90%+ | Orange → Red `#FF4400` → `#FF0000` |

GPU type is auto-detected (NVIDIA via `nvidia-smi`, AMD/Intel via sysfs). Readings are averaged over a configurable window to prevent flickering. Lights turn off cleanly on Ctrl-C.

### AlienWare x17 R1 recommended usage

The x17 R1 ships with an NVIDIA discrete GPU (RTX 3070/3080). The most useful configurations:

```bash
# Keyboard as a live GPU strain gauge — responsive 1s updates
python gpu_monitor.py --zone keyboard --gpu nvidia --interval 1

# Lightbar only — subtle background indicator while you work
python gpu_monitor.py --zone lightbar --gpu nvidia --interval 2

# All zones at once for maximum visibility during gaming/rendering
python gpu_monitor.py --zone all --gpu nvidia --interval 1 --smooth 4

# High-frequency polling with heavier smoothing — fluid, no flicker
python gpu_monitor.py --zone keyboard --gpu nvidia --interval 0.5 --smooth 6
```

### General examples

```bash
# Basic — auto-detect GPU, control all zones, poll every 2s
python gpu_monitor.py

# Custom zone and interval
python gpu_monitor.py --zone keyboard --interval 1

# Force GPU type, increase smoothing window
python gpu_monitor.py --gpu nvidia --smooth 5

# Just the lightbar as a subtle strain indicator
python gpu_monitor.py --zone lightbar --interval 0.5
```

What it looks like in the terminal:

```
  GPU  73.4%  ████████████████████████████░░░░░░░░░░░░  #77FF00
```

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--zone` / `-z` | `all` | Zone(s) to control |
| `--gpu` / `-g` | auto | `nvidia`, `amd`, or `intel` |
| `--interval` / `-i` | `2.0` | Poll interval in seconds |
| `--smooth` / `-s` | `3` | Readings to average (reduces flicker) |
| `--host` | `localhost` | OpenRGB SDK host |
| `--port` / `-p` | `6742` | OpenRGB SDK port |

---

## Files

| File                | Description                                           |
|---------------------|-------------------------------------------------------|
| `alienware_rgb.py`  | Main RGB controller — standalone, no heavy deps       |
| `gpu_monitor.py`    | GPU load → live color gradient monitor                |
| `setup.sh`          | One-time setup for Linux (pip install + symlink)      |
