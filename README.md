# alienware-rgb

A Linux (and Windows) Python CLI for controlling RGB lighting zones on the **AlienWare x17 R1** — keyboard, alien logo, lightbar, power button, touchpad, and more.

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

## Files

| File                | Description                                      |
|---------------------|--------------------------------------------------|
| `alienware_rgb.py`  | Main script — standalone, no heavy dependencies  |
| `setup.sh`          | One-time setup for Linux (pip install + symlink) |
