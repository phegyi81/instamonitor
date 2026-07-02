# InstaMonitor Troubleshooting Guide

## Table of Contents
1. [Common Issues](#common-issues)
2. [Installation Problems](#installation-problems)
3. [Capture Issues](#capture-issues)
4. [Classification Problems](#classification-problems)
5. [Performance Issues](#performance-issues)
6. [Database Issues](#database-issues)
7. [Diagnostic Commands](#diagnostic-commands)

---

## Common Issues

### Service Won't Start

**Symptoms:** Service fails to start or immediately stops

**Diagnosis:**
```bash
# Check service status
/etc/init.d/instamonitor status

# View system logs
logread | tail -50

# Check for process errors
ps | grep -E "(capture|analyzer)"
```

**Solutions:**

1. **Check dependencies:**
```bash
opkg list-installed | grep -E "(python3|tcpdump)"
```
If missing, install:
```bash
opkg update
opkg install python3-light python3-sqlite3 tcpdump
```

2. **Verify file permissions:**
```bash
chmod +x /etc/instamonitor/capture.sh
chmod +x /etc/instamonitor/analyzer.py
chmod +x /etc/init.d/instamonitor
```

3. **Check configuration:**
```bash
cat /etc/instamonitor/config.conf
# Ensure no syntax errors
```

4. **Verify directories exist:**
```bash
mkdir -p /var/lib/instamonitor
mkdir -p /tmp/instamonitor
```

---

### No Traffic Being Captured

**Symptoms:** Packet log file is empty or not growing

**Diagnosis:**
```bash
# Check if tcpdump is running
ps | grep tcpdump

# Test tcpdump manually
tcpdump -i br-lan -c 10 -n

# Check packet log
ls -lh /tmp/instamonitor/packet_log.txt
tail /tmp/instamonitor/packet_log.txt
```

**Solutions:**

1. **Verify correct interface:**
```bash
# List interfaces
ifconfig

# Update config if needed
vi /etc/instamonitor/config.conf
# Set correct CAPTURE_INTERFACE
```

2. **Check IP filter lists:**
```bash
# Ensure IP files exist and have content
cat /etc/instamonitor/instagram_ips.txt
cat /etc/instamonitor/tiktok_ips.txt

# Test without IP filtering
tcpdump -i br-lan "tcp port 443" -c 10
```

3. **Verify network activity:**
```bash
# Monitor all HTTPS traffic
tcpdump -i br-lan "tcp port 443" -n -c 20
```

---

### No Classifications / All Unknown

**Symptoms:** Analyzer runs but classifies everything as "unknown"

**Diagnosis:**
```bash
# Check analyzer output
tail -f /var/log/instamonitor.log

# Verify packet data format
head -20 /tmp/instamonitor/packet_log.txt
```

**Solutions:**

1. **Check packet log format:**
Expected format: `timestamp|src_ip|dst_ip|length`
```bash
# View sample entries
head -5 /tmp/instamonitor/packet_log.txt
```

2. **Adjust classification thresholds:**
```bash
vi /etc/instamonitor/config.conf
# Try more lenient thresholds:
CHAT_PACKET_SIZE_MAX=800
SCROLL_MIN_AVG_SIZE=1000
```

3. **Enable debug logging:**
```bash
vi /etc/instamonitor/config.conf
# Set: LOG_LEVEL=DEBUG
/etc/init.d/instamonitor restart
tail -f /var/log/instamonitor.log
```

4. **Verify flow duration:**
Flows need at least 5 packets to be classified. If sessions are very short, increase flow timeout:
```bash
vi /etc/instamonitor/analyzer.py
# Find: self.flow_timeout = 60
# Change to: self.flow_timeout = 120
```

---

## Installation Problems

### Insufficient Storage

**Symptoms:** Installation fails with "No space left on device"

**Solutions:**

1. **Check available space:**
```bash
df -h
```

2. **Clean up space:**
```bash
# Remove old package lists
rm -rf /tmp/opkg-lists/*

# Clean package cache
opkg clean

# Remove old kernels/modules if safe
opkg list-installed | grep kernel
```

3. **Use external storage:**
```bash
# Mount USB drive
mkdir -p /mnt/usb
mount /dev/sda1 /mnt/usb

# Change install locations in install.sh
LIB_DIR="/mnt/usb/instamonitor"
```

### Package Installation Fails

**Symptoms:** opkg install fails

**Solutions:**

1. **Update package lists:**
```bash
opkg update
```

2. **Check internet connectivity:**
```bash
ping -c 3 8.8.8.8
ping -c 3 downloads.openwrt.org
```

3. **Try alternative mirrors:**
```bash
# Check /etc/opkg.conf
cat /etc/opkg.conf
```

4. **Install manually:**
```bash
# Download package manually
cd /tmp
wget http://downloads.openwrt.org/releases/22.03.2/packages/mips_24kc/packages/python3-light_3.10.9-1_mips_24kc.ipk
opkg install python3-light_3.10.9-1_mips_24kc.ipk
```

---

## Capture Issues

### High Packet Loss

**Symptoms:** Warning messages about dropped packets

**Solutions:**

1. **Increase buffer size:**
```bash
vi /etc/instamonitor/capture.sh
# Find tcpdump line with -B option
# Increase: -B 2048 to -B 4096
```

2. **Reduce snapshot length:**
```bash
vi /etc/instamonitor/config.conf
SNAPSHOT_LENGTH=64  # from 96
```

3. **Filter more aggressively:**
Only capture specific devices:
```bash
vi /etc/instamonitor/capture.sh
# Add to filter: "and host 192.168.1.100"
```

### Interface Not Found

**Symptoms:** "Device not found" error

**Solutions:**

1. **List available interfaces:**
```bash
ifconfig -a
ip link show
```

2. **Common interface names:**
- `br-lan` - LAN bridge (most common)
- `eth0` / `eth1` - Ethernet interfaces
- `wlan0` - Wireless interface

3. **Update configuration:**
```bash
vi /etc/instamonitor/config.conf
CAPTURE_INTERFACE=br-lan  # or your interface name
```

---

## Classification Problems

### All Traffic Classified as Video Scrolling

**Symptoms:** Chat and video calls not being detected

**Solutions:**

1. **Check bidirectional ratio:**
```bash
# Add diagnostic output to analyzer.py
vi /etc/instamonitor/analyzer.py
# In classify_flow, add print statements:
print(f"Bidir ratio: {bidir_ratio}, DL ratio: {download_ratio}")
```

2. **Adjust thresholds:**
```bash
vi /etc/instamonitor/config.conf
# More sensitive chat detection
CHAT_MAX_PACKETS_PER_SEC=30
VIDEO_CONF_BIDIRECTIONAL_RATIO=0.2  # from 0.3
```

### Misclassification Between Activities

**Symptoms:** Video calls classified as scrolling, etc.

**Solutions:**

1. **Observe actual patterns:**
```bash
# Enable debug mode
vi /etc/instamonitor/config.conf
LOG_LEVEL=DEBUG

# Use the app while monitoring
tail -f /var/log/instamonitor.log
```

2. **Tune specific thresholds:**
Based on observations, adjust in `config.conf`:
```bash
# For your specific network:
CHAT_PACKET_SIZE_MAX=450
VIDEO_CONF_MIN_SIZE=400
VIDEO_CONF_MAX_SIZE=1400
SCROLL_MIN_AVG_SIZE=1600
```

3. **Consider network conditions:**
On slow networks, packet sizes may be different. Adjust accordingly.

---

## Performance Issues

### High CPU Usage

**Symptoms:** Router becomes slow, high CPU in top

**Diagnosis:**
```bash
top -b -n 1 | grep -E "(capture|analyzer|tcpdump)"
```

**Solutions:**

1. **Increase analysis interval:**
```bash
vi /etc/instamonitor/config.conf
ANALYSIS_INTERVAL=30  # from 10
```

2. **Reduce packet capture rate:**
```bash
vi /etc/instamonitor/capture.sh
# Add rate limiting to tcpdump:
# After tcpdump command, add: | pv -L 100k
```

3. **Limit to specific times:**
Create a cron job to stop/start:
```bash
# Stop at night
0 23 * * * /etc/init.d/instamonitor stop
# Start in morning
0 7 * * * /etc/init.d/instamonitor start
```

4. **Use nice/ionice:**
```bash
vi /etc/init.d/instamonitor
# Add nice -n 19 before commands
nice -n 19 $PROG_CAPTURE
```

### High Memory Usage

**Symptoms:** Out of memory errors, system instability

**Solutions:**

1. **Reduce buffer size:**
```bash
vi /etc/instamonitor/config.conf
BUFFER_SIZE=5000  # from 10000
```

2. **Increase flow cleanup frequency:**
```bash
vi /etc/instamonitor/analyzer.py
# Find flow_timeout, reduce it:
self.flow_timeout = 30  # from 60
```

3. **Process in smaller batches:**
```bash
vi /etc/instamonitor/config.conf
BATCH_SIZE=50  # from 100
```

### Storage Filling Up

**Symptoms:** Disk full errors

**Solutions:**

1. **Enable automatic cleanup:**
```bash
vi /etc/instamonitor/config.conf
DB_ROTATION_ENABLED=true
DB_MAX_SIZE_MB=50  # from 100
```

2. **Manual cleanup:**
```bash
# Clean old data
sqlite3 /var/lib/instamonitor/usage.db << EOF
DELETE FROM flow_classifications WHERE timestamp < datetime('now', '-7 days');
DELETE FROM traffic_stats WHERE timestamp < datetime('now', '-7 days');
VACUUM;
EOF
```

3. **Clean packet logs:**
```bash
# Truncate packet log (analyzer will recreate)
> /tmp/instamonitor/packet_log.txt
```

---

## Database Issues

### Database Locked

**Symptoms:** "database is locked" errors

**Solutions:**

1. **Stop competing processes:**
```bash
/etc/init.d/instamonitor stop
sleep 2
/etc/init.d/instamonitor start
```

2. **Check for stale locks:**
```bash
lsof /var/lib/instamonitor/usage.db
# Kill any stale processes
```

3. **Increase timeout:**
```bash
vi /etc/instamonitor/database.py
# Add to get_connection:
conn.execute("PRAGMA busy_timeout = 30000")  # 30 seconds
```

### Corrupted Database

**Symptoms:** SQLite errors, integrity check failures

**Solutions:**

1. **Check integrity:**
```bash
sqlite3 /var/lib/instamonitor/usage.db "PRAGMA integrity_check;"
```

2. **Backup and rebuild:**
```bash
# Backup current database
cp /var/lib/instamonitor/usage.db /tmp/usage.db.backup

# Dump data
sqlite3 /var/lib/instamonitor/usage.db .dump > /tmp/dump.sql

# Recreate database
rm /var/lib/instamonitor/usage.db
sqlite3 /var/lib/instamonitor/usage.db < /tmp/dump.sql
```

3. **Start fresh:**
```bash
# Backup for analysis
cp /var/lib/instamonitor/usage.db /tmp/usage.db.old

# Remove and recreate
rm /var/lib/instamonitor/usage.db
/etc/init.d/instamonitor restart
```

---

## Diagnostic Commands

### Complete System Check

Run this comprehensive diagnostic:

```bash
cat > /tmp/instamonitor_diag.sh << 'EOF'
#!/bin/sh

echo "========================================="
echo "InstaMonitor Diagnostic Report"
echo "========================================="
echo ""

echo "=== System Info ==="
uname -a
uptime
echo ""

echo "=== Disk Space ==="
df -h
echo ""

echo "=== Memory ==="
free
echo ""

echo "=== Installed Packages ==="
opkg list-installed | grep -E "(python3|tcpdump|sqlite)"
echo ""

echo "=== Service Status ==="
/etc/init.d/instamonitor status 2>&1
echo ""

echo "=== Running Processes ==="
ps | grep -E "(capture|analyzer|tcpdump)" | grep -v grep
echo ""

echo "=== Configuration ==="
cat /etc/instamonitor/config.conf
echo ""

echo "=== IP Lists ==="
echo "Instagram IPs:"
wc -l /etc/instamonitor/instagram_ips.txt
echo "TikTok IPs:"
wc -l /etc/instamonitor/tiktok_ips.txt
echo ""

echo "=== File Sizes ==="
ls -lh /etc/instamonitor/
ls -lh /var/lib/instamonitor/
ls -lh /tmp/instamonitor/ 2>/dev/null
echo ""

echo "=== Database Size ==="
du -h /var/lib/instamonitor/usage.db 2>/dev/null || echo "No database yet"
echo ""

echo "=== Recent Logs ==="
logread | grep instamonitor | tail -20
echo ""

echo "=== Packet Log Status ==="
if [ -f /tmp/instamonitor/packet_log.txt ]; then
    echo "File exists"
    wc -l /tmp/instamonitor/packet_log.txt
    echo "Sample lines:"
    head -3 /tmp/instamonitor/packet_log.txt
else
    echo "Packet log not found"
fi
echo ""

echo "=== Network Interfaces ==="
ifconfig | grep -E "^[a-z]|inet addr"
echo ""

echo "========================================="
echo "Diagnostic Complete"
echo "========================================="
EOF

chmod +x /tmp/instamonitor_diag.sh
/tmp/instamonitor_diag.sh
```

### Export Diagnostic Report

```bash
# Run diagnostic and save to file
/tmp/instamonitor_diag.sh > /tmp/diagnostic_report.txt

# Copy to computer
scp root@router:/tmp/diagnostic_report.txt ~/Downloads/
```

---

## Getting Help

If you're still experiencing issues:

1. **Run the diagnostic script above**
2. **Check logs carefully:** `logread | grep instamonitor`
3. **Test components individually:**
   - Run capture.sh manually
   - Run analyzer.py manually
   - Test database.py
4. **Check the GitHub issues** for similar problems
5. **Create a new issue** with:
   - Diagnostic report
   - Steps to reproduce
   - Expected vs actual behavior
   - Router model and OpenWrt version

---

## Advanced Debugging

### Enable Python Debugging

```bash
vi /etc/instamonitor/analyzer.py
# Add at top of main():
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Trace Packet Flow

```bash
# Terminal 1: Watch captures
tail -f /tmp/instamonitor/packet_log.txt

# Terminal 2: Watch analyzer
tail -f /var/log/instamonitor.log

# Terminal 3: Test with specific app
# Use Instagram/TikTok on phone
```

### Network Packet Analysis

```bash
# Capture sample for analysis
tcpdump -i br-lan -w /tmp/sample.pcap -c 1000 "tcp port 443"

# Transfer to computer and open in Wireshark
scp root@router:/tmp/sample.pcap ~/Downloads/

# Analyze patterns in Wireshark:
# - Statistics -> Conversations
# - Statistics -> I/O Graphs
# - Analyze packet sizes and timing
```

This will help you understand actual traffic patterns and tune classification accordingly.
