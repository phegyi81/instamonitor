#!/bin/sh
#
# InstaMonitor Packet Capture Script
# Optimized for OpenWrt with minimal resource usage
#
# Usage: capture.sh [config_file]
#   config_file: Optional path to configuration file
#                If not specified, uses config.conf next to this script.
#

# Resolve the directory this script lives in.
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)

# Load configuration
if [ -n "$1" ]; then
    CONFIG_FILE="$1"
else
    CONFIG_FILE="$SCRIPT_DIR/config.conf"
fi

if [ -f "$CONFIG_FILE" ]; then
    . "$CONFIG_FILE"
else
    echo "ERROR: Configuration file not found: $CONFIG_FILE"
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

# Default values if not set in config
CAPTURE_INTERFACE=${CAPTURE_INTERFACE:-br-lan}
SNAPSHOT_LENGTH=${SNAPSHOT_LENGTH:-96}
OUTPUT_DIR=$(resolve_path "${OUTPUT_DIR:-data}")

# Create output directory
mkdir -p "$OUTPUT_DIR"

# Build a device-based filter: monitor only the configured device IP(s).
# Everything the device does on 443 is captured; the analyzer resolves each
# remote IP's owner on the fly and the classifier sorts target vs background.
build_device_filter() {
    local filter=""
    local first=1
    for ip in $DEVICE_IPS; do
        if [ $first -eq 1 ]; then
            filter="(host $ip"
            first=0
        else
            filter="$filter or host $ip"
        fi
    done
    if [ $first -eq 0 ]; then
        echo "$filter)"
    else
        echo ""
    fi
}

# Check if tcpdump is installed
if ! command -v tcpdump >/dev/null 2>&1; then
    echo "ERROR: tcpdump is not installed. Install with: opkg install tcpdump"
    exit 1
fi

# Build the filter (monitor the configured device IP(s) on HTTPS/QUIC).
DEV_FILTER=$(build_device_filter)
if [ -z "$DEV_FILTER" ]; then
    echo "ERROR: DEVICE_IPS is empty in config.conf."
    echo "Set DEVICE_IPS to the LAN IP(s) of the phone(s) to monitor."
    exit 1
fi
FILTER="$DEV_FILTER and (tcp port 443 or udp port 443)"

echo "Starting packet capture on $CAPTURE_INTERFACE"
echo "Filter: $FILTER"
echo "Output: $OUTPUT_DIR/packet_log.txt"

# Cleanup function
cleanup() {
    echo "Stopping packet capture..."
    kill $TCPDUMP_PID 2>/dev/null
    exit 0
}

trap cleanup INT TERM

# Start tcpdump with optimized settings
# -i: interface to monitor
# -s: snapshot length (capture only headers, not full packets)
# -n: don't resolve hostnames (faster)
# -t: don't print timestamps in output (we generate our own)
# -l: line buffered output (for real-time processing)
# -q: quiet output (less verbose, just essential info)
# -B: buffer size in KB
tcpdump -i "$CAPTURE_INTERFACE" \
    -s "$SNAPSHOT_LENGTH" \
    -n -t -l -q \
    -B 2048 \
    "$FILTER" | \
    awk -f "$SCRIPT_DIR/parse_packets.awk" >> "$OUTPUT_DIR/packet_log.txt" &

TCPDUMP_PID=$!

echo "Packet capture started (PID: $TCPDUMP_PID)"
echo "Log file: $OUTPUT_DIR/packet_log.txt"

# Wait for tcpdump process
wait $TCPDUMP_PID
