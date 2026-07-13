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

packages="python3-light python3-decimal tcpdump"

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
chmod +x "$SCRIPT_DIR/features.py"
chmod +x "$SCRIPT_DIR/model.py"
chmod +x "$SCRIPT_DIR/ipinfo.py"
chmod +x "$SCRIPT_DIR/label.sh"
chmod +x "$SCRIPT_DIR/run.sh"
[ -f "$SCRIPT_DIR/train.py" ] && chmod +x "$SCRIPT_DIR/train.py"

echo ""
echo "========================================="
echo "Setup completed successfully!"
echo "========================================="
echo ""
echo "Everything runs from this directory: $SCRIPT_DIR"
echo ""
echo "Next steps:"
echo "1. Edit config.conf and set DEVICE_IPS to your phone's LAN IP:"
echo "   vi $SCRIPT_DIR/config.conf"
echo ""
echo "2. Record labeled training sessions (one activity at a time):"
echo "   $SCRIPT_DIR/label.sh chat        300"
echo "   $SCRIPT_DIR/label.sh video_call  300"
echo "   $SCRIPT_DIR/label.sh reels       300"
echo "   $SCRIPT_DIR/label.sh other       300   # normal usage, NO Instagram/TikTok"
echo ""
echo "3. Train the model ON YOUR LAPTOP (needs: pip install scikit-learn):"
echo "   scp $SCRIPT_DIR/data/training_data.csv features.py train.py laptop:"
echo "   ./train.py --input training_data.csv --output model.json"
echo "   scp model.json  router:$SCRIPT_DIR/"
echo ""
echo "4. Start monitoring: $SCRIPT_DIR/run.sh   (Ctrl+C to stop)"
echo "5. View stats:      $SCRIPT_DIR/stats.py --today"
echo ""
echo "NOTE: scikit-learn is NOT installed on the router -- training happens on"
echo "      your laptop; only the tiny model.json runs here."
echo ""
echo "To run in the background:"
echo "   $SCRIPT_DIR/run.sh > $SCRIPT_DIR/data/instamonitor.log 2>&1 &"
echo ""

