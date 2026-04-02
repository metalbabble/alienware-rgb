#!/usr/bin/env bash
# Setup script for alienware_rgb.py — AlienWare x17 R1 RGB controller
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_NAME="alienware-rgb"

echo "==> Installing Python dependency: openrgb-python"
pip install --user openrgb-python

echo ""
echo "==> Making script executable"
chmod +x "$SCRIPT_DIR/alienware_rgb.py"

echo ""
echo "==> Creating symlink at ~/.local/bin/$INSTALL_NAME"
mkdir -p ~/.local/bin
ln -sf "$SCRIPT_DIR/alienware_rgb.py" ~/.local/bin/$INSTALL_NAME

# Check PATH
if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
    echo ""
    echo "  NOTE: Add ~/.local/bin to your PATH by adding this to ~/.bashrc or ~/.zshrc:"
    echo "    export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

echo ""
echo "==> Done! You can now run:"
echo ""
echo "    $INSTALL_NAME --help"
echo "    $INSTALL_NAME --list-zones"
echo "    $INSTALL_NAME --zone all --color FF0000"
echo "    $INSTALL_NAME --zone keyboard --effect rainbow"
echo ""
echo "==> OpenRGB setup:"
echo ""
echo "    Install OpenRGB:  https://openrgb.org/"
echo "      Ubuntu/Debian:  sudo apt install openrgb   (or AppImage from website)"
echo ""
echo "    Run OpenRGB SDK server (keep this running in the background):"
echo "      openrgb --server"
echo ""
echo "    Or enable it in the GUI:  Edit → Settings → SDK Server → Start Server"
echo ""
