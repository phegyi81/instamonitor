#!/bin/sh
#
# InstaMonitor Setup Script for OpenWrt
#
# Installs the required system packages and makes the project scripts
# executable. Everything runs from this directory - nothing is copied
# to system locations and no files are created outside this folder.
#

set -e

echo "========================================="
echo "InstaMonitor Setup for OpenWrt"
echo "========================================="
echo ""

# Resolve the directory this script lives in.
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)

# Check if running as root (needed for opkg)
if [ "$(id -u)" != "0" ]; then
    echo "ERROR: This script must be run as root (needed to install packages)"
    exit 1
fi

# Update package list
echo "Updating package list..."
opkg update

# Install required packages
echo ""
echo "Installing required packages..."

packages="python3-light tcpdump"

for pkg in $packages; do
    if ! opkg list-installed | grep -q "^$pkg "; then
        echo "Installing $pkg..."
        opkg install "$pkg"
    else
        echo "$pkg is already installed"
    fi
done

# Make project scripts executable
echo ""
echo "Making scripts executable..."
chmod +x "$SCRIPT_DIR/capture.sh"
chmod +x "$SCRIPT_DIR/analyzer.py"
chmod +x "$SCRIPT_DIR/database.py"
chmod +x "$SCRIPT_DIR/stats.py"
chmod +x "$SCRIPT_DIR/run.sh"

echo ""
echo "========================================="
echo "Setup completed successfully!"
echo "========================================="
echo ""
echo "Everything runs from this directory: $SCRIPT_DIR"
echo ""
echo "Next steps:"
echo "1. Review and edit configuration: vi $SCRIPT_DIR/config.conf"
echo "2. Update IP addresses if needed:"
echo "   - Instagram: $SCRIPT_DIR/instagram_ips.txt"
echo "   - TikTok: $SCRIPT_DIR/tiktok_ips.txt"
echo "3. Start monitoring: $SCRIPT_DIR/run.sh"
echo "   (Press Ctrl+C to stop)"
echo "4. View stats: $SCRIPT_DIR/stats.py --today"
echo ""
echo "To run in the background:"
echo "   $SCRIPT_DIR/run.sh > $SCRIPT_DIR/data/instamonitor.log 2>&1 &"
echo ""

