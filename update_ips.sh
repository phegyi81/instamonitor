#!/bin/sh
#
# IP Address Update Helper for InstaMonitor
# Helps discover and update Instagram/TikTok IP addresses
#

# Resolve the directory this script lives in, so it works self-contained.
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
CONFIG_DIR="$SCRIPT_DIR"
INSTAGRAM_IPS="$CONFIG_DIR/instagram_ips.txt"
TIKTOK_IPS="$CONFIG_DIR/tiktok_ips.txt"

echo "========================================="
echo "InstaMonitor IP Address Update Helper"
echo "========================================="
echo ""

# Function to discover IPs via DNS
discover_ips() {
    local domain=$1
    local service=$2
    
    echo "Discovering IPs for $service..."
    echo "Domains to check: $domain"
    echo ""
    
    # Use dig if available, otherwise nslookup
    if command -v dig >/dev/null 2>&1; then
        for d in $domain; do
            echo "  $d:"
            dig +short $d A | grep -E '^[0-9]+\.' | sort -u | while read ip; do
                echo "    $ip"
                # Get whois info to find network range
                if command -v whois >/dev/null 2>&1; then
                    whois $ip | grep -E '^(CIDR|inetnum|NetRange)' | head -1
                fi
            done
        done
    else
        for d in $domain; do
            echo "  $d:"
            nslookup $d | grep '^Address:' | grep -v '#' | awk '{print $2}' | sort -u
        done
    fi
    echo ""
}

# Function to monitor DNS queries
monitor_dns() {
    local pattern=$1
    local duration=${2:-60}
    
    echo "Monitoring DNS queries for pattern: $pattern"
    echo "Duration: ${duration} seconds"
    echo "Use the app on your device during this time..."
    echo ""
    
    # Enable DNS logging temporarily
    uci set dhcp.@dnsmasq[0].logqueries=1
    uci commit dhcp
    /etc/init.d/dnsmasq restart
    
    sleep 2
    
    # Monitor for specified duration
    timeout $duration logread -f | grep dnsmasq | grep -iE "$pattern" &
    MONITOR_PID=$!
    
    sleep $duration
    kill $MONITOR_PID 2>/dev/null
    
    # Disable DNS logging
    uci set dhcp.@dnsmasq[0].logqueries=0
    uci commit dhcp
    /etc/init.d/dnsmasq restart
    
    echo ""
    echo "Monitoring complete"
    echo ""
}

# Function to capture actual traffic
capture_traffic() {
    local duration=${1:-30}
    
    echo "Capturing HTTPS traffic for $duration seconds..."
    echo "Use Instagram/TikTok on your device now..."
    echo ""
    
    timeout $duration tcpdump -i br-lan -n "tcp port 443 or udp port 443" 2>/dev/null | \
        grep -oE '[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+' | \
        sort -u | \
        while read ip; do
            # Filter out local IPs
            case $ip in
                192.168.*|10.*|172.16.*|127.*)
                    ;;
                *)
                    echo "  Found external IP: $ip"
                    ;;
            esac
        done
    
    echo ""
    echo "Capture complete"
    echo ""
}

# Function to add IP to list
add_ip_to_list() {
    local ip=$1
    local file=$2
    
    if grep -q "^$ip" "$file" 2>/dev/null; then
        echo "  IP already in list: $ip"
        return 1
    else
        echo "$ip" >> "$file"
        echo "  Added: $ip"
        return 0
    fi
}

# Main menu
while true; do
    echo "========================================="
    echo "Select an option:"
    echo "1) Discover Instagram IPs via DNS"
    echo "2) Discover TikTok IPs via DNS"
    echo "3) Monitor DNS queries (Instagram)"
    echo "4) Monitor DNS queries (TikTok)"
    echo "5) Capture actual traffic (requires usage)"
    echo "6) View current Instagram IPs"
    echo "7) View current TikTok IPs"
    echo "8) Add IP manually"
    echo "9) Stop InstaMonitor (restart manually with run.sh)"
    echo "0) Exit"
    echo "========================================="
    echo -n "Choice: "
    read choice
    
    echo ""
    
    case $choice in
        1)
            discover_ips "instagram.com www.instagram.com i.instagram.com api.instagram.com scontent.cdninstagram.com" "Instagram"
            ;;
        2)
            discover_ips "tiktok.com www.tiktok.com api.tiktok.com v16-webapp.tiktok.com" "TikTok"
            ;;
        3)
            monitor_dns "instagram" 60
            ;;
        4)
            monitor_dns "tiktok" 60
            ;;
        5)
            capture_traffic 30
            ;;
        6)
            echo "Current Instagram IPs:"
            echo "======================"
            if [ -f "$INSTAGRAM_IPS" ]; then
                cat "$INSTAGRAM_IPS"
            else
                echo "File not found: $INSTAGRAM_IPS"
            fi
            echo ""
            ;;
        7)
            echo "Current TikTok IPs:"
            echo "=================="
            if [ -f "$TIKTOK_IPS" ]; then
                cat "$TIKTOK_IPS"
            else
                echo "File not found: $TIKTOK_IPS"
            fi
            echo ""
            ;;
        8)
            echo -n "Enter IP or CIDR range: "
            read ip_range
            echo ""
            echo "Add to:"
            echo "1) Instagram"
            echo "2) TikTok"
            echo -n "Choice: "
            read platform
            
            case $platform in
                1)
                    add_ip_to_list "$ip_range" "$INSTAGRAM_IPS"
                    ;;
                2)
                    add_ip_to_list "$ip_range" "$TIKTOK_IPS"
                    ;;
                *)
                    echo "Invalid choice"
                    ;;
            esac
            echo ""
            ;;
        9)
            echo "Stopping InstaMonitor (if running)..."
            killall run.sh tcpdump analyzer.py 2>/dev/null
            echo "Restart it manually with: $SCRIPT_DIR/run.sh"
            echo ""
            ;;
        0)
            echo "Exiting..."
            exit 0
            ;;
        *)
            echo "Invalid choice"
            echo ""
            ;;
    esac
    
    echo "Press Enter to continue..."
    read dummy
done
