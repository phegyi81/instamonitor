# Quick Start Guide

Get InstaMonitor up and running in 5 minutes!

## Prerequisites

- OpenWrt router (tested on version 22.03+)
- SSH access to your router
- At least 50MB free storage space
- Basic command-line knowledge

## Step 1: Transfer Files to Router

On your computer, from the `instamonitor` directory:

```bash
# Replace 192.168.1.1 with your router's IP
scp -r * root@192.168.1.1:/tmp/instamonitor/
```

If the directory doesn't exist on the router:
```bash
ssh root@192.168.1.1 "mkdir -p /tmp/instamonitor"
```

## Step 2: SSH into Router

```bash
ssh root@192.168.1.1
```

## Step 3: Run Installation

```bash
cd /tmp/instamonitor
sh install.sh
```

The installer will:
- Update package lists
- Install required packages (Python3, tcpdump)
- Create necessary directories
- Copy configuration files
- Install the `run.sh` launcher and stats utility

**This may take 5-10 minutes depending on your internet connection.**

> Prefer not to install? You can run everything straight from the source
> directory: `sh run.sh config.conf`

## Step 4: Verify Installation

```bash
# Check installed files
ls -la /etc/instamonitor/

# Test CSV storage module
python3 /etc/instamonitor/database.py
```

## Step 5: Configure (Optional)

The default configuration works for most cases, but you can customize:

```bash
vi /etc/instamonitor/config.conf
```

Key settings:
- `CAPTURE_INTERFACE` - Your network interface (default: br-lan)
- `ANALYSIS_INTERVAL` - How often to analyze (default: 10 seconds)
- `DATA_DIR` - Where to store CSV files

## Step 6: Start Monitoring

Run in the foreground (press Ctrl+C to stop):

```bash
/etc/instamonitor/run.sh
```

Or run in the background and log the output:

```bash
/etc/instamonitor/run.sh > /var/log/instamonitor.log 2>&1 &
```

## Step 7: Verify It's Working

Check processes:
```bash
ps | grep -E "(capture|analyzer|tcpdump)"
```

You should see:
- `capture.sh` - Capturing packets
- `analyzer.py` - Analyzing traffic
- `tcpdump` - Actual packet capture

Watch real-time analysis (foreground run prints to the terminal, or tail your log file):
```bash
tail -f /var/log/instamonitor.log
```

## Step 8: Test with Real Traffic

1. Use Instagram or TikTok on a device connected to your WiFi
2. Scroll through videos for 30-60 seconds
3. Check the statistics:

```bash
instamonitor-stats --today
```

You should see entries for:
- Platform (instagram/tiktok)
- Activity type (chat/video_conference/video_scroll)
- Duration and data usage

## Example Output

```
Statistics for all devices
Period: 2026-07-02 to 2026-07-02

================================================================================
Platform     Activity             Duration        Data            Sessions  
================================================================================
instagram    video_scroll         00:02:30        45.75 MB        1         
tiktok       video_scroll         00:01:45        38.50 MB        1         
================================================================================
TOTAL                             00:04:15        84.25 MB                 
================================================================================
```

## Troubleshooting Quick Checks

### Nothing being captured?

1. **Check interface name:**
```bash
ifconfig
# Update CAPTURE_INTERFACE in config.conf if needed
```

2. **Test tcpdump manually:**
```bash
tcpdump -i br-lan -c 10
```

### No classifications?

1. **Check if IP addresses are correct:**
```bash
cat /etc/instamonitor/instagram_ips.txt
cat /etc/instamonitor/tiktok_ips.txt
```

2. **Update IP addresses:**
```bash
sh /etc/instamonitor/update_ips.sh
# Choose option 1 or 2 to discover current IPs
```

### High CPU usage?

1. **Increase analysis interval:**
```bash
vi /etc/instamonitor/config.conf
# Set: ANALYSIS_INTERVAL=30
# Then stop (Ctrl+C) and restart run.sh
```

## Next Steps

Now that InstaMonitor is running:

1. **Monitor for 24 hours** to gather meaningful data
2. **Review statistics daily** using `instamonitor-stats`
3. **Update IP addresses monthly** using `update_ips.sh`
4. **Tune classification** based on your observations

## Useful Commands

```bash
# Start monitoring (foreground, Ctrl+C to stop)
/etc/instamonitor/run.sh

# Start in the background
/etc/instamonitor/run.sh > /var/log/instamonitor.log 2>&1 &

# Stop a background run
killall run.sh tcpdump analyzer.py

# View today's stats
instamonitor-stats --today

# View stats for specific device
instamonitor-stats --device 192.168.1.100 --week

# Export data
instamonitor-stats --today --export /tmp/stats.csv

# Watch live analysis (when running in the background)
tail -f /var/log/instamonitor.log

# Update IP addresses
sh /etc/instamonitor/update_ips.sh
```

## Getting Help

- **Detailed usage guide:** See [USAGE.md](USAGE.md)
- **Troubleshooting:** See [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
- **Understanding classifications:** See "Understanding Classifications" in USAGE.md

## Important Notes

### Privacy & Legal

- Inform users that network monitoring is active
- Only use on networks you have authority to monitor
- Comply with local privacy laws

### Accuracy

- Classifications are based on traffic patterns, not packet content
- Accuracy improves over time as patterns become clearer
- Some activities may be misclassified initially
- Update IP addresses regularly for best results

### Performance

- Designed for routers with 64MB+ RAM
- Uses ~5-15% CPU on typical hardware
- Monitor resource usage: `top` command
- Tune settings if experiencing issues

## Advantages of CSV Format

✅ **Universal compatibility** - Works with Excel, Google Sheets, databases, programming languages  
✅ **Human readable** - Can view/edit with any text editor  
✅ **Easy to backup** - Simple file copy  
✅ **No dependencies** - No need for SQLite or other databases  
✅ **Portable** - Transfer between systems easily  
✅ **Tool agnostic** - Use any analysis tool you prefer  
✅ **Simple** - No complex queries needed for basic analysis  
✅ **Lightweight** - Smaller than many database formats  
✅ **Debuggable** - Easy to inspect and validate data  

See [CSV_FORMAT.md](CSV_FORMAT.md) for complete format documentation and analysis examples.

## Success Checklist

- [ ] Installation completed without errors
- [ ] `run.sh` starts and runs
- [ ] Packet capture is working (packet log file growing)
- [ ] Analyzer is running (output shows classifications)
- [ ] CSV files are being updated
- [ ] Statistics command shows data
- [ ] Classifications appear reasonable

If all items are checked, you're all set! 🎉

---

**Need help?** Check [TROUBLESHOOTING.md](TROUBLESHOOTING.md) or create an issue on GitHub.
