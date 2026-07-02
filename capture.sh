#!/bin/sh
#
# InstaMonitor Packet Capture Script
# Optimized for OpenWrt with minimal resource usage
#

# Load configuration
CONFIG_FILE="/etc/instamonitor/config.conf"
if [ -f "$CONFIG_FILE" ]; then
    . "$CONFIG_FILE"
else
    echo "ERROR: Configuration file not found: $CONFIG_FILE"
    exit 1
fi

# Default values if not set in config
CAPTURE_INTERFACE=${CAPTURE_INTERFACE:-br-lan}
SNAPSHOT_LENGTH=${SNAPSHOT_LENGTH:-96}
OUTPUT_DIR=${OUTPUT_DIR:-/tmp/instamonitor}
FIFO_PATH="${OUTPUT_DIR}/capture.fifo"

# Create output directory
mkdir -p "$OUTPUT_DIR"

# Create named pipe for packet data if it doesn't exist
if [ ! -p "$FIFO_PATH" ]; then
    mkfifo "$FIFO_PATH"
fi

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
            
            if [ $first -eq 1 ]; then
                filter="(host $ip"
                first=0
            else
                filter="$filter or host $ip"
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
            
            if [ $first -eq 1 ]; then
                filter="(host $ip"
                first=0
            else
                filter="$filter or host $ip"
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
echo "Output: $FIFO_PATH"

# Cleanup function
cleanup() {
    echo "Stopping packet capture..."
    kill $TCPDUMP_PID 2>/dev/null
    rm -f "$FIFO_PATH"
    exit 0
}

trap cleanup INT TERM

# Start tcpdump with optimized settings
# -i: interface
# -s: snapshot length (capture only headers)
# -n: don't resolve hostnames (faster)
# -t: don't print timestamps (less output)
# -l: line buffered output
# -q: quiet output (less verbose)
# -B: buffer size in KB
tcpdump -i "$CAPTURE_INTERFACE" \
    -s "$SNAPSHOT_LENGTH" \
    -n -l -q \
    -B 2048 \
    "$FILTER" \
    -w - 2>/dev/null | tee "$FIFO_PATH" | \
    # Output packet metadata in simple format
    tcpdump -n -t -r - 2>/dev/null | \
    awk -v output="$OUTPUT_DIR/packet_log.txt" '
    {
        # Parse tcpdump output: timestamp src > dst: flags, length
        # Extract: timestamp, src_ip, dst_ip, protocol, length
        
        gsub(/[,:]/, " ")
        
        # Get timestamp
        timestamp = systime()
        
        # Parse source and destination
        if ($2 ~ />/) {
            src = $1
            dst = $3
        }
        
        # Extract length (usually last field or marked as "length")
        for (i = 1; i <= NF; i++) {
            if ($i == "length") {
                length = $(i+1)
                break
            }
        }
        if (length == "") {
            # Try to find number at end
            length = $NF
            if (length !~ /^[0-9]+$/) length = 0
        }
        
        # Output: timestamp|src|dst|length
        print timestamp "|" src "|" dst "|" length >> output
        
        # Flush every 10 packets to avoid buffer buildup
        if (NR % 10 == 0) {
            close(output)
        }
    }
    ' &

TCPDUMP_PID=$!

echo "Packet capture started (PID: $TCPDUMP_PID)"
echo "Log file: $OUTPUT_DIR/packet_log.txt"

# Wait for tcpdump process
wait $TCPDUMP_PID
