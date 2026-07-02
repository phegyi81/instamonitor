# InstaMonitor Usage Guide

## Table of Contents
1. [Quick Start](#quick-start)
2. [Monitoring Traffic](#monitoring-traffic)
3. [Viewing Statistics](#viewing-statistics)
4. [Understanding Classifications](#understanding-classifications)
5. [Updating IP Addresses](#updating-ip-addresses)
6. [Performance Tuning](#performance-tuning)
7. [Data Export](#data-export)

## Quick Start

### Starting InstaMonitor

```bash
# Start the service
/etc/init.d/instamonitor start

# Check if it's running
ps | grep -E "(capture|analyzer)"

# View real-time logs
logread -f | grep instamonitor
```

### Stopping InstaMonitor

```bash
# Stop the service
/etc/init.d/instamonitor stop

# Verify it stopped
ps | grep -E "(capture|analyzer)"
```

## Monitoring Traffic

### Real-time Monitoring

Watch the analyzer output in real-time:

```bash
tail -f /var/log/instamonitor.log
```

You'll see classifications like:
```
192.168.1.100 -> video_scroll: 45.2s, 387 packets, 1250.5KB down
192.168.1.101 -> chat: 12.5s, 48 packets, 25.3KB down
192.168.1.102 -> video_conference: 180.3s, 2401 packets, 850.2KB down
```

### Check Service Status

```bash
# Check if service is enabled
/etc/init.d/instamonitor enabled && echo "Enabled" || echo "Disabled"

# View process status
top -b -n 1 | grep -E "(capture|analyzer|tcpdump)"
```

## Viewing Statistics

### Today's Statistics

```bash
instamonitor-stats --today
```

Output:
```
Statistics for all devices
Period: 2026-07-02 to 2026-07-02

================================================================================
Platform     Activity             Duration        Data            Sessions  
================================================================================
instagram    chat                 00:15:30        5.25 MB         12        
instagram    video_scroll         02:30:15        450.75 MB       8         
tiktok       video_scroll         01:45:20        380.50 MB       15        
tiktok       video_conference     00:25:10        125.25 MB       2         
================================================================================
TOTAL                             04:56:15        961.75 MB                 
================================================================================
```

### Device-Specific Statistics

```bash
# View stats for a specific device
instamonitor-stats --device 192.168.1.100 --today

# Last week's stats
instamonitor-stats --device 192.168.1.100 --week

# All-time stats
instamonitor-stats --device 192.168.1.100
```

### Export to CSV

```bash
# Export today's data
instamonitor-stats --today --export /tmp/stats_today.csv

# Transfer to your computer
scp root@router:/tmp/stats_today.csv ~/Downloads/
```

## Understanding Classifications

### Activity Types

#### 1. **Chat** (Messaging/DMs)
- **Characteristics:**
  - Small packet sizes (< 500 bytes average)
  - Bidirectional traffic (both sending and receiving)
  - Sporadic packet timing
  - 2-20 packets per second

- **What it captures:**
  - Direct messages
  - Comments being typed and sent
  - Story replies
  - Quick reactions

#### 2. **Video Conference** (Live streaming/calls)
- **Characteristics:**
  - Medium packet sizes (500-1500 bytes)
  - Steady bidirectional flow
  - Consistent packet rate (10+ packets/sec)
  - At least 30% traffic in both directions

- **What it captures:**
  - Instagram/TikTok Live watching
  - Live streaming participation
  - Video calls (if supported)

#### 3. **Video Scroll** (Content browsing)
- **Characteristics:**
  - Large packets (> 1500 bytes average)
  - Mostly download traffic (80%+)
  - Bursty patterns (video loading)
  - Variable packet rate

- **What it captures:**
  - Scrolling through feed
  - Watching Reels/TikToks
  - Browsing Stories
  - Loading images and videos

#### 4. **Unknown**
- Traffic that doesn't fit the above patterns
- Very short sessions
- Unusual traffic patterns
- May include app updates, API calls, etc.

## Updating IP Addresses

Instagram and TikTok periodically change their server IPs. Update them to maintain accuracy:

### Finding Current IPs

```bash
# On your router
dig instagram.com +short
dig i.instagram.com +short
dig api.instagram.com +short

dig tiktok.com +short
dig www.tiktok.com +short
```

### Method 1: DNS Monitoring

Monitor DNS queries to see which domains are being accessed:

```bash
# Enable DNS logging in OpenWrt
uci set dhcp.@dnsmasq[0].logqueries=1
uci commit dhcp
/etc/init.d/dnsmasq restart

# Watch DNS queries
logread -f | grep dnsmasq | grep -E "(instagram|tiktok)"
```

### Method 2: Network Capture

Capture HTTPS traffic temporarily and see destinations:

```bash
tcpdump -i br-lan -n "tcp port 443" | grep -E "(instagram|tiktok)"
```

### Adding New IPs

1. Edit the IP list files:
```bash
vi /etc/instamonitor/instagram_ips.txt
vi /etc/instamonitor/tiktok_ips.txt
```

2. Add new IP ranges (one per line):
```
157.240.50.0/24
```

3. Restart InstaMonitor:
```bash
/etc/init.d/instamonitor restart
```

### Automatic IP Discovery Script

Create a helper script to discover IPs:

```bash
cat > /tmp/find_social_ips.sh << 'EOF'
#!/bin/sh
echo "Instagram IPs:"
dig +short instagram.com i.instagram.com api.instagram.com | sort -u

echo -e "\nTikTok IPs:"
dig +short tiktok.com www.tiktok.com api.tiktok.com | sort -u
EOF

chmod +x /tmp/find_social_ips.sh
/tmp/find_social_ips.sh
```

## Performance Tuning

### Reducing CPU Usage

If InstaMonitor is using too much CPU:

1. **Increase analysis interval** (analyze less frequently):
```bash
vi /etc/instamonitor/config.conf
# Change: ANALYSIS_INTERVAL=10
# To:     ANALYSIS_INTERVAL=30
```

2. **Reduce snapshot length** (capture fewer bytes):
```bash
# Change: SNAPSHOT_LENGTH=96
# To:     SNAPSHOT_LENGTH=64
```

3. **Limit to specific devices** (modify capture filter):
```bash
vi /etc/instamonitor/capture.sh
# Add device filter in build_filter function
```

### Reducing Memory Usage

1. **Decrease buffer size**:
```bash
vi /etc/instamonitor/config.conf
# Change: BUFFER_SIZE=10000
# To:     BUFFER_SIZE=5000
```

2. **Enable more aggressive cleanup**:
```bash
vi /etc/instamonitor/config.conf
# Change: DB_MAX_SIZE_MB=100
# To:     DB_MAX_SIZE_MB=50
```

### Reducing Storage Usage

1. **Enable database rotation**:
```bash
vi /etc/instamonitor/config.conf
# Ensure: DB_ROTATION_ENABLED=true
```

2. **Clean old data manually**:
```bash
sqlite3 /var/lib/instamonitor/usage.db "DELETE FROM flow_classifications WHERE timestamp < datetime('now', '-7 days');"
sqlite3 /var/lib/instamonitor/usage.db "VACUUM;"
```

## Data Export

### CSV Export

```bash
# Export all data
instamonitor-stats --export /tmp/all_stats.csv

# Export specific device
instamonitor-stats --device 192.168.1.100 --week --export /tmp/device_stats.csv
```

### Direct Database Access

```bash
# Open database
sqlite3 /var/lib/instamonitor/usage.db

# Example queries:
# List all devices
SELECT * FROM devices;

# Total usage per device today
SELECT d.ip_address, 
       SUM(s.total_duration_seconds) as total_seconds,
       SUM(s.total_bytes) as total_bytes
FROM daily_summaries s
JOIN devices d ON s.device_id = d.id
WHERE s.date = date('now')
GROUP BY d.ip_address;

# Activity breakdown
SELECT activity_type, 
       COUNT(*) as sessions,
       AVG(duration_seconds) as avg_duration
FROM sessions
WHERE date(start_time) = date('now')
GROUP BY activity_type;
```

### Automated Reports

Create a daily report script:

```bash
cat > /etc/instamonitor/daily_report.sh << 'EOF'
#!/bin/sh
DATE=$(date +%Y-%m-%d)
REPORT="/tmp/instamonitor_report_$DATE.txt"

echo "InstaMonitor Daily Report - $DATE" > $REPORT
echo "=======================================" >> $REPORT
echo "" >> $REPORT

instamonitor-stats --today >> $REPORT

# Optionally email or upload the report
# mail -s "Daily InstaMonitor Report" user@example.com < $REPORT
EOF

chmod +x /etc/instamonitor/daily_report.sh

# Add to cron (run at midnight)
echo "0 0 * * * /etc/instamonitor/daily_report.sh" >> /etc/crontabs/root
/etc/init.d/cron restart
```

## Tips and Best Practices

### Accuracy Tips

1. **Keep IP lists updated** - Check monthly for changes
2. **Monitor for 24 hours** - Patterns become clearer over time
3. **Consider time zones** - Usage patterns vary by time of day
4. **Multiple devices** - Compare patterns across devices

### Privacy Considerations

1. **Inform users** - Let people know monitoring is active
2. **Secure the database** - Protect stored data
3. **Regular cleanup** - Don't keep data longer than needed
4. **Access control** - Limit who can view statistics

### Maintenance

1. **Weekly** - Check logs for errors
2. **Monthly** - Update IP addresses, clean old data
3. **Quarterly** - Review and adjust classification thresholds
4. **Yearly** - Full system review and optimization

## Advanced Usage

### Custom Classification Thresholds

Adjust thresholds based on observed patterns:

```bash
vi /etc/instamonitor/config.conf

# Make chat detection more sensitive
CHAT_PACKET_SIZE_MAX=600
CHAT_MAX_PACKETS_PER_SEC=30

# Adjust video scroll detection
SCROLL_MIN_AVG_SIZE=1200
SCROLL_DOWNLOAD_RATIO=0.75
```

### Integration with Other Tools

1. **Grafana Dashboard** - Visualize data over time
2. **Home Assistant** - Track usage as sensor data
3. **Custom Scripts** - Parse database for automation
4. **Parental Controls** - Trigger alerts based on usage

### Debugging Classification

Enable detailed logging:

```bash
vi /etc/instamonitor/config.conf
# Change: LOG_LEVEL=INFO
# To:     LOG_LEVEL=DEBUG

/etc/init.d/instamonitor restart
tail -f /var/log/instamonitor.log
```

This will show detailed information about each flow and why it was classified a certain way.
