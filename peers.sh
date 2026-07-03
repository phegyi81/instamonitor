#!/bin/sh
#
# InstaMonitor Peer Discovery Helper
#
# Captures live traffic to/from a given device and lists the remote IPs
# (peers) it talks to on HTTPS/QUIC (TCP/UDP port 443), sorted by how many
# packets were exchanged. Use it while watching Reels/TikToks to find the
# real server IP ranges, then add them to instagram_ips.txt / tiktok_ips.txt.
#
# Usage: peers.sh <device_ip> [duration_seconds] [interface]
#   device_ip        IP address of the device to inspect (required)
#   duration_seconds how long to capture (default: 30)
#   interface        capture interface (default: br-lan)
#
# Example:
#   sh peers.sh 192.168.1.100 30 br-lan
#

DEVICE_IP="$1"
DURATION="${2:-30}"
INTERFACE="${3:-br-lan}"

if [ -z "$DEVICE_IP" ]; then
    echo "Usage: $0 <device_ip> [duration_seconds] [interface]"
    echo "Example: $0 192.168.1.100 30 br-lan"
    exit 1
fi

if ! command -v tcpdump >/dev/null 2>&1; then
    echo "ERROR: tcpdump is not installed. Install with: opkg install tcpdump"
    exit 1
fi

# Portable timeout: some OpenWrt/busybox builds lack the `timeout` applet.
# Provides `timeout <seconds> <command...>` via background + sleep + kill.
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

echo "========================================="
echo "InstaMonitor Peer Discovery"
echo "========================================="
echo "Device:    $DEVICE_IP"
echo "Interface: $INTERFACE"
echo "Duration:  ${DURATION}s"
echo ""
echo "Use the app on the device now (watch Reels / TikToks)..."
echo ""

# Capture packets to/from the device on port 443 (TCP and UDP/QUIC),
# extract the remote peer IP from each line, and count packets per peer.
timeout "$DURATION" tcpdump -i "$INTERFACE" -n -t -q \
    "host $DEVICE_IP and (tcp port 443 or udp port 443)" | \
    awk -v dev="$DEVICE_IP" '
    {
        # tcpdump line: IP <src.port> > <dst.port>: ...
        if ($3 != ">") next

        src = $2
        dst = $4
        gsub(/:/, "", dst)

        # Strip the trailing ".port" to leave the bare IPv4 address
        sub(/\.[0-9]+$/, "", src)
        sub(/\.[0-9]+$/, "", dst)

        # The peer is whichever endpoint is not the device
        if (src == dev) peer = dst
        else if (dst == dev) peer = src
        else next

        count[peer]++
        total++
    }
    END {
        for (p in count) print count[p], p
    }' | sort -rn > /tmp/instamonitor_peers.$$

if [ ! -s /tmp/instamonitor_peers.$$ ]; then
    echo "No peer traffic captured for $DEVICE_IP on port 443."
    echo "Check that:"
    echo "  - the device IP is correct (see: cat /tmp/dhcp.leases)"
    echo "  - the interface is correct (try: ip link)"
    echo "  - you actually used the app during the capture window"
    rm -f /tmp/instamonitor_peers.$$
    exit 0
fi

echo "Remote peers (most active first):"
echo "-----------------------------------------"
printf "  %-18s %s\n" "PEER IP" "PACKETS"
while read cnt ip; do
    printf "  %-18s %6d\n" "$ip" "$cnt"
done < /tmp/instamonitor_peers.$$

peers=$(wc -l < /tmp/instamonitor_peers.$$)
echo "-----------------------------------------"
echo "Unique peers: $peers"
echo ""
echo "Tip: add the relevant ranges to your IP lists, e.g.:"
echo "  echo '157.240.0.0/16' >> $(cd "$(dirname "$0")" && pwd)/instagram_ips.txt"
echo "Then restart run.sh."

rm -f /tmp/instamonitor_peers.$$
