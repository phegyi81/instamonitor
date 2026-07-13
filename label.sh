#!/bin/sh
#
# InstaMonitor Labeled Session Recorder
# =====================================
# Captures traffic for ONE device for a fixed duration, tags every resulting
# flow with a label, and appends the feature rows to the training dataset.
#
# Run one activity at a time, purely, with other apps closed so the labels
# stay clean. Record a dedicated "other" session (normal usage WITHOUT
# Instagram/TikTok) so the model learns what background traffic looks like.
#
# Usage:
#   label.sh <label> [duration_seconds] [device_ip] [interface]
#
#   label        one of: chat, video_call, reels, other  (any string works)
#   duration     seconds to record (default 300 = 5 minutes)
#   device_ip    LAN IP of the phone (default: first entry in DEVICE_IPS)
#   interface    capture interface (default: CAPTURE_INTERFACE / br-lan)
#
# Example:
#   ./label.sh reels 300 192.168.1.100
#

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)

# Portable timeout shim: OpenWrt busybox may lack the 'timeout' applet.
if ! command -v timeout >/dev/null 2>&1; then
    timeout() {
        _timeout_secs="$1"; shift
        "$@" &
        _timeout_cmd_pid=$!
        ( sleep "$_timeout_secs"; kill "$_timeout_cmd_pid" 2>/dev/null ) &
        _timeout_killer_pid=$!
        wait "$_timeout_cmd_pid" 2>/dev/null
        _timeout_rc=$?
        kill "$_timeout_killer_pid" 2>/dev/null
        return $_timeout_rc
    }
fi

CONFIG_FILE="$SCRIPT_DIR/config.conf"
[ -f "$CONFIG_FILE" ] && . "$CONFIG_FILE"

CONFIG_DIR="$SCRIPT_DIR"
resolve_path() {
    case "$1" in
        /*) echo "$1" ;;
        *) echo "$CONFIG_DIR/$1" ;;
    esac
}

# --- Arguments ---------------------------------------------------------------
LABEL="$1"
DURATION="${2:-300}"
DEVICE_IP="$3"
IFACE="${4:-${CAPTURE_INTERFACE:-br-lan}}"

if [ -z "$LABEL" ]; then
    echo "Usage: $0 <label> [duration_seconds] [device_ip] [interface]"
    echo "  label: chat | video_call | reels | other (or any string)"
    exit 1
fi

# Device IP: fall back to the first entry of DEVICE_IPS from config.
if [ -z "$DEVICE_IP" ]; then
    DEVICE_IP=$(echo "${DEVICE_IPS:-}" | awk '{print $1}')
fi
if [ -z "$DEVICE_IP" ]; then
    echo "ERROR: no device IP given and DEVICE_IPS not set in config.conf."
    echo "Pass it explicitly:  $0 $LABEL $DURATION 192.168.1.100"
    exit 1
fi

SNAP="${SNAPSHOT_LENGTH:-96}"
OUTPUT_DIR=$(resolve_path "${OUTPUT_DIR:-data}")
TRAINING_CSV="$OUTPUT_DIR/training_data.csv"
MIN_PKTS="${MIN_FLOW_PACKETS:-5}"
mkdir -p "$OUTPUT_DIR"

if ! command -v tcpdump >/dev/null 2>&1; then
    echo "ERROR: tcpdump is not installed. Install with: opkg install tcpdump"
    exit 1
fi

SESSION_LOG="$OUTPUT_DIR/label_${LABEL}_$(date +%s).raw"

echo "========================================="
echo "Recording labeled session"
echo "========================================="
echo "Label:      $LABEL"
echo "Device IP:  $DEVICE_IP"
echo "Interface:  $IFACE"
echo "Duration:   ${DURATION}s"
echo "Session log:$SESSION_LOG"
echo "========================================="
echo ""
echo ">>> Do ONLY '$LABEL' activity now (close other apps). Recording..."

# Capture only this device's encrypted traffic, parse to flow records.
timeout "$DURATION" tcpdump -i "$IFACE" -s "$SNAP" -n -t -l -q \
    "host $DEVICE_IP and (tcp port 443 or udp port 443)" 2>/dev/null | \
    awk -f "$SCRIPT_DIR/parse_packets.awk" >> "$SESSION_LOG"

PACKETS=$(wc -l < "$SESSION_LOG" 2>/dev/null | tr -d ' ')
echo ""
echo "Captured $PACKETS packet records."

if [ "${PACKETS:-0}" -eq 0 ]; then
    echo "WARNING: no packets captured. Check the device IP and interface,"
    echo "and make sure traffic was actually flowing."
    rm -f "$SESSION_LOG"
    exit 1
fi

echo "Extracting flow features and appending to $TRAINING_CSV ..."
python3 "$SCRIPT_DIR/features.py" \
    --input "$SESSION_LOG" \
    --label "$LABEL" \
    --output "$TRAINING_CSV" \
    --append \
    --min-packets "$MIN_PKTS"

# The raw per-packet log is no longer needed once features are extracted.
rm -f "$SESSION_LOG"

echo ""
echo "Done. Record the other activities the same way, then train on your"
echo "laptop with:  ./train.py --input $TRAINING_CSV --output model.json"
