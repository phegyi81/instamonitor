#!/bin/sh
#
# InstaMonitor Installation Script for OpenWrt
#

set -e

echo "========================================="
echo "InstaMonitor Installation for OpenWrt"
echo "========================================="
echo ""

# Check if running as root
if [ "$(id -u)" != "0" ]; then
    echo "ERROR: This script must be run as root"
    exit 1
fi

# Configuration
INSTALL_DIR="/etc/instamonitor"
BIN_DIR="/usr/bin"
LIB_DIR="/var/lib/instamonitor"
LOG_DIR="/var/log"
INIT_SCRIPT="/etc/init.d/instamonitor"

echo "Installation directories:"
echo "  Config:   $INSTALL_DIR"
echo "  Binaries: $BIN_DIR"
echo "  Data:     $LIB_DIR"
echo "  Logs:     $LOG_DIR"
echo ""

# Check available space
available_space=$(df / | awk 'NR==2 {print $4}')
required_space=51200  # 50MB in KB

if [ "$available_space" -lt "$required_space" ]; then
    echo "WARNING: Low disk space. Available: ${available_space}KB, Required: ${required_space}KB"
    echo "Continue anyway? (y/n)"
    read -r response
    if [ "$response" != "y" ]; then
        exit 1
    fi
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

# Create directories
echo ""
echo "Creating directories..."
mkdir -p "$INSTALL_DIR"
mkdir -p "$LIB_DIR"
mkdir -p "$LOG_DIR"
mkdir -p /tmp/instamonitor

# Copy configuration files
echo ""
echo "Installing configuration files..."
cp config.conf "$INSTALL_DIR/"
cp instagram_ips.txt "$INSTALL_DIR/"
cp tiktok_ips.txt "$INSTALL_DIR/"

# Copy scripts
echo ""
echo "Installing scripts..."
cp capture.sh "$INSTALL_DIR/"
cp analyzer.py "$INSTALL_DIR/"
cp database.py "$INSTALL_DIR/"
chmod +x "$INSTALL_DIR/capture.sh"
chmod +x "$INSTALL_DIR/analyzer.py"
chmod +x "$INSTALL_DIR/database.py"

# Create init script
echo ""
echo "Creating init script..."
cat > "$INIT_SCRIPT" << 'EOF'
#!/bin/sh /etc/rc.common

START=99
STOP=10

USE_PROCD=1

PROG_CAPTURE=/etc/instamonitor/capture.sh
PROG_ANALYZER=/etc/instamonitor/analyzer.py
CONFIG=/etc/instamonitor/config.conf

start_service() {
    echo "Starting InstaMonitor..."
    
    # Start packet capture
    procd_open_instance capture
    procd_set_param command $PROG_CAPTURE
    procd_set_param respawn
    procd_set_param stdout 1
    procd_set_param stderr 1
    procd_close_instance
    
    # Wait a bit for capture to start
    sleep 2
    
    # Start analyzer
    procd_open_instance analyzer
    procd_set_param command $PROG_ANALYZER $CONFIG /tmp/instamonitor/packet_log.txt
    procd_set_param respawn
    procd_set_param stdout 1
    procd_set_param stderr 1
    procd_close_instance
    
    echo "InstaMonitor started"
}

stop_service() {
    echo "Stopping InstaMonitor..."
    killall -9 capture.sh 2>/dev/null || true
    killall -9 analyzer.py 2>/dev/null || true
    killall -9 tcpdump 2>/dev/null || true
    echo "InstaMonitor stopped"
}
EOF

chmod +x "$INIT_SCRIPT"

# Create stats utility script
echo ""
echo "Creating stats utility..."
cat > "$BIN_DIR/instamonitor-stats" << 'EOF'
#!/usr/bin/env python3
"""InstaMonitor Statistics Utility - CSV Edition"""

import sys
import os
import csv
from datetime import datetime, timedelta
import argparse
from collections import defaultdict

def format_bytes(bytes_val):
    """Format bytes in human-readable format"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_val < 1024.0:
            return f"{bytes_val:.2f} {unit}"
        bytes_val /= 1024.0
    return f"{bytes_val:.2f} TB"

def format_duration(seconds):
    """Format seconds as hours:minutes:seconds"""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"

def read_daily_stats(data_dir, device_ip=None, start_date=None, end_date=None):
    """Read daily statistics from CSV"""
    daily_file = os.path.join(data_dir, 'daily_stats.csv')
    if not os.path.exists(daily_file):
        return []
    
    stats = defaultdict(lambda: {'total_seconds': 0, 'total_bytes': 0, 'sessions': 0})
    
    with open(daily_file, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if device_ip and row['device_ip'] != device_ip:
                continue
            if start_date and row['date'] < start_date:
                continue
            if end_date and row['date'] > end_date:
                continue
            
            key = (row['device_ip'], row['platform'], row['activity_type'])
            stats[key]['total_seconds'] += float(row['total_duration_seconds'])
            stats[key]['total_bytes'] += int(row['total_bytes'])
            stats[key]['sessions'] += int(row['flow_count'])
    
    result = []
    for (dev_ip, platform, activity), data in stats.items():
        result.append({
            'device_ip': dev_ip,
            'platform': platform,
            'activity_type': activity,
            'total_seconds': data['total_seconds'],
            'total_bytes': data['total_bytes'],
            'sessions': data['sessions']
        })
    return result

def main():
    parser = argparse.ArgumentParser(description='InstaMonitor Statistics')
    parser.add_argument('--device', help='Device IP address')
    parser.add_argument('--today', action='store_true', help='Show today\'s stats')
    parser.add_argument('--yesterday', action='store_true', help='Show yesterday\'s stats')
    parser.add_argument('--week', action='store_true', help='Show this week\'s stats')
    parser.add_argument('--export', help='Export to CSV file')
    parser.add_argument('--data-dir', default='/var/lib/instamonitor', help='Data directory')
    
    args = parser.parse_args()
    
    data_dir = args.data_dir
    
    # Determine date range
    if args.today:
        start_date = datetime.now().date()
        end_date = start_date
    elif args.yesterday:
        start_date = (datetime.now() - timedelta(days=1)).date()
        end_date = start_date
    elif args.week:
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=7)
    else:
        start_date = None
        end_date = None
    
    # Get stats
    if args.device:
        stats = read_daily_stats(data_dir, args.device, start_date, end_date)
        print(f"\nStatistics for {args.device}")
    else:
        print("\nOverall Statistics")
        stats = read_daily_stats(data_dir, None, start_date, end_date)
    
    if start_date:
        print(f"Period: {start_date} to {end_date}")
    else:
        print("Period: All time")
    
    print("\n" + "="*80)
    print(f"{'Platform':<12} {'Activity':<20} {'Duration':<15} {'Data':<15} {'Sessions':<10}")
    print("="*80)
    
    total_seconds = 0
    total_bytes = 0
    
    for stat in stats:
        duration = format_duration(int(stat['total_seconds']))
        data = format_bytes(int(stat['total_bytes']))
        
        print(f"{stat['platform']:<12} {stat['activity_type']:<20} "
              f"{duration:<15} {data:<15} {stat['sessions']:<10}")
        
        total_seconds += stat['total_seconds']
        total_bytes += stat['total_bytes']
    
    print("="*80)
    print(f"{'TOTAL':<12} {'':<20} {format_duration(int(total_seconds)):<15} "
          f"{format_bytes(int(total_bytes)):<15}")
    print("="*80)
    
    if args.export:
        # Export to CSV
        with open(args.export, 'w') as f:
            f.write("Device IP,Platform,Activity,Duration (seconds),Bytes,Sessions\n")
            for stat in stats:
                f.write(f"{stat.get('device_ip', 'All')},{stat['platform']},{stat['activity_type']},"
                       f"{stat['total_seconds']},{stat['total_bytes']},"
                       f"{stat['sessions']}\n")
        print(f"\nExported to {args.export}")

if __name__ == '__main__':
    main()
EOF

chmod +x "$BIN_DIR/instamonitor-stats"

# Enable service
echo ""
echo "Enabling InstaMonitor service..."
"$INIT_SCRIPT" enable

echo ""
echo "========================================="
echo "Installation completed successfully!"
echo "========================================="
echo ""
echo "Next steps:"
echo "1. Review and edit configuration: vi $INSTALL_DIR/config.conf"
echo "2. Update IP addresses if needed:"
echo "   - Instagram: $INSTALL_DIR/instagram_ips.txt"
echo "   - TikTok: $INSTALL_DIR/tiktok_ips.txt"
echo "3. Start the service: /etc/init.d/instamonitor start"
echo "4. Check logs: logread | grep instamonitor"
echo "5. View stats: instamonitor-stats --today"
echo ""
echo "The service will start automatically on boot."
echo ""
