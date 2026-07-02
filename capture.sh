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
INSTAGRAM_IPS=$(resolve_path "${INSTAGRAM_IPS:-instagram_ips.txt}")
TIKTOK_IPS=$(resolve_path "${TIKTOK_IPS:-tiktok_ips.txt}")

# Create output directory
mkdir -p "$OUTPUT_DIR"

# Build tcpdump filter for Instagram and TikTok
build_filter() {
    local filter=""
    local first=1
    
    # Read Instagram IPs
    if [ -f "$INSTAGRAM_IPS" ]; then
        while read -r ip; do
            # Skip comments and empty lines
            case "$ip" in
                \#*|"") continue ;;
            esac

            # Networks (CIDR) require 'net'; single addresses use 'host'
            case "$ip" in
                */*) kw="net" ;;
                *) kw="host" ;;
            esac

            if [ $first -eq 1 ]; then
                filter="($kw $ip"
                first=0
            else
                filter="$filter or $kw $ip"
            fi
        done < "$INSTAGRAM_IPS"
    fi
    
    # Read TikTok IPs
    if [ -f "$TIKTOK_IPS" ]; then
        while read -r ip; do
            # Skip comments and empty lines
            case "$ip" in
                \#*|"") continue ;;
            esac

            # Networks (CIDR) require 'net'; single addresses use 'host'
            case "$ip" in
                */*) kw="net" ;;
                *) kw="host" ;;
            esac

            if [ $first -eq 1 ]; then
                filter="($kw $ip"
                first=0
            else
                filter="$filter or $kw $ip"
            fi
        done < "$TIKTOK_IPS"
    fi
    
    if [ $first -eq 0 ]; then
        filter="$filter)"
        echo "$filter"
    else
        echo ""
    fi
}

# Check if tcpdump is installed
if ! command -v tcpdump >/dev/null 2>&1; then
    echo "ERROR: tcpdump is not installed. Install with: opkg install tcpdump"
    exit 1
fi

# Build the filter
FILTER=$(build_filter)

if [ -z "$FILTER" ]; then
    echo "WARNING: No IP addresses configured. Monitoring all HTTPS traffic."
    FILTER="tcp port 443"
else
    # Add HTTPS/QUIC port filters
    FILTER="($FILTER) and (tcp port 443 or udp port 443)"
fi

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
    awk -v output="$OUTPUT_DIR/packet_log.txt" '
    {
        # Parse tcpdump output format:
        # IP 192.168.100.89.40514 > 216.239.34.223.443: tcp 0
        
        # Get current timestamp
        timestamp = systime()
        
        # Check if this is a valid packet line (has > separator)
        if ($3 == ">") {
            # Extract source IP (remove port)
            # Format: IP.IP.IP.IP.port
            src = ""
            n = split($2, src_parts, ".")
            if (n > 4) {
                src = src_parts[1] "." src_parts[2] "." src_parts[3] "." src_parts[4]
            }
            
            # Extract destination IP (remove port and trailing colon)
            # Format: IP.IP.IP.IP.port: or IP.IP.IP.IP.port
            dst = ""
            dst_field = $4
            gsub(/:/, "", dst_field)
            n = split(dst_field, dst_parts, ".")
            if (n > 4) {
                dst = dst_parts[1] "." dst_parts[2] "." dst_parts[3] "." dst_parts[4]
            }
            
            # Extract packet length
            length = 0
            for (i = 1; i <= NF; i++) {
                if ($i == "length") {
                    length = $(i+1)
                    break
                }
            }
            if (length == 0 && match($NF, /^[0-9]+$/)) {
                length = $NF
            }
            
            # Output if we successfully parsed everything
            if (src != "" && dst != "" && length != "") {
                print timestamp "|" src "|" dst "|" length
                
                # Flush periodically
                if (NR % 10 == 0) {
                    fflush()
                }
            }
        }
    }' >> "$OUTPUT_DIR/packet_log.txt" &

TCPDUMP_PID=$!

echo "Packet capture started (PID: $TCPDUMP_PID)"
echo "Log file: $OUTPUT_DIR/packet_log.txt"

# Wait for tcpdump process
wait $TCPDUMP_PID
