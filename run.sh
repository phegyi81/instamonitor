#!/bin/sh
#
# InstaMonitor Launcher
# Starts packet capture and traffic analyzer together.
# Press Ctrl+C to stop both cleanly.
#
# Usage: run.sh [config_file]
#   config_file: Optional path to configuration file
#                If not specified, uses config.conf next to this script.
#

# Resolve the directory this script lives in, so everything runs
# self-contained from the project directory.
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)

# Determine config file
if [ -n "$1" ]; then
    CONFIG_FILE="$1"
else
    CONFIG_FILE="$SCRIPT_DIR/config.conf"
fi

if [ ! -f "$CONFIG_FILE" ]; then
    echo "ERROR: Configuration file not found: $CONFIG_FILE"
    echo "Usage: $0 [config_file]"
    exit 1
fi

# Base directory for resolving relative paths from the config file.
CONFIG_DIR=$(cd "$(dirname "$CONFIG_FILE")" && pwd)

# Resolve a possibly-relative path against the config directory.
resolve_path() {
    case "$1" in
        /*) echo "$1" ;;
        *) echo "$CONFIG_DIR/$1" ;;
    esac
}

# Load configuration to find paths
. "$CONFIG_FILE"
OUTPUT_DIR=$(resolve_path "${OUTPUT_DIR:-data}")
PACKET_LOG="$OUTPUT_DIR/packet_log.txt"

# Locate scripts in the script directory
CAPTURE_SCRIPT="$SCRIPT_DIR/capture.sh"
ANALYZER_SCRIPT="$SCRIPT_DIR/analyzer.py"

echo "========================================="
echo "InstaMonitor"
echo "========================================="
echo "Config:   $CONFIG_FILE"
echo "Capture:  $CAPTURE_SCRIPT"
echo "Analyzer: $ANALYZER_SCRIPT"
echo "========================================="
echo ""

# Cleanup function: stop both child processes on exit
cleanup() {
    echo ""
    echo "Stopping InstaMonitor..."
    [ -n "$CAPTURE_PID" ] && kill "$CAPTURE_PID" 2>/dev/null
    [ -n "$ANALYZER_PID" ] && kill "$ANALYZER_PID" 2>/dev/null
    # Make sure tcpdump children are gone
    killall tcpdump 2>/dev/null
    echo "Stopped."
    exit 0
}

trap cleanup INT TERM

# Start packet capture in the background
echo "Starting packet capture..."
sh "$CAPTURE_SCRIPT" "$CONFIG_FILE" &
CAPTURE_PID=$!

# Give the capture a moment to create the packet log
sleep 2

# Start the analyzer in the background
echo "Starting traffic analyzer..."
python3 "$ANALYZER_SCRIPT" "$CONFIG_FILE" "$PACKET_LOG" &
ANALYZER_PID=$!

echo ""
echo "InstaMonitor is running. Press Ctrl+C to stop."
echo ""

# Wait for either process to exit, then clean up the other
wait
