# InstaMonitor - Social Media Traffic Analysis for OpenWrt

A lightweight network monitoring system for OpenWrt routers that analyzes Instagram and TikTok usage patterns by examining traffic metadata and patterns.

## Features

- **Traffic Classification**: Distinguishes between chatting, video conferencing, and video scrolling
- **Lightweight**: Optimized for resource-constrained OpenWrt devices
- **Privacy-Focused**: Only analyzes packet metadata, not encrypted content
- **CSV Storage**: Simple, portable CSV files for easy analysis with any tool
- **Real-time Monitoring**: Continuous traffic capture and analysis

## How It Works

The system analyzes encrypted HTTPS traffic patterns to infer activity types:

- **Chatting**: Small packets (< 500 bytes), bidirectional, frequent but sporadic
- **Video Conferencing**: Medium-large packets (500-1500 bytes), consistent bidirectional flow, steady rate
- **Video Scrolling**: Large packets (> 1500 bytes average), mostly download, bursty patterns

## Components

1. **capture.sh** - Packet capture using tcpdump with filters
2. **analyzer.py** - Traffic pattern analysis and classification
3. **config.conf** - Configuration for IP ranges and thresholds
4. **install.sh** - Installation script for OpenWrt
5. **database.py** - CSV file management and aggregation

## System Requirements

- OpenWrt 22.03+ (tested on Netgear WNDR3700 v4)
- Available storage: ~50MB
- Python3 (lightweight edition)
- tcpdump package

## Installation

```bash
# 1. Transfer files to router
scp -r instamonitor root@router:/tmp/

# 2. SSH into router
ssh root@router

# 3. Run installation script
cd /tmp/instamonitor
sh install.sh

# 4. Start monitoring
/etc/init.d/instamonitor start
```

## Configuration

Edit `/etc/instamonitor/config.conf`:

```ini
# IP ranges for social media platforms (updated periodically)
INSTAGRAM_IPS=/etc/instamonitor/instagram_ips.txt
TIKTOK_IPS=/etc/instamonitor/tiktok_ips.txt

# Classification thresholds
CHAT_PACKET_SIZE=500
VIDEO_CONF_MIN_SIZE=500
VIDEO_CONF_MAX_SIZE=1500
SCROLL_MIN_SIZE=1500

# Data Storage
DATA_DIR=/var/lib/instamonitor

# Capture settings
CAPTURE_INTERFACE=br-lan
SNAPSHOT_LENGTH=96
```

## Usage

```bash
# Start monitoring
/etc/init.d/instamonitor start

# Stop monitoring
/etc/init.d/instamonitor stop

# View statistics
instamonitor-stats --today
instamonitor-stats --device <MAC_ADDRESS>
instamonitor-stats --export /tmp/report.csv
```

## Data Storage

The system stores data in simple CSV files for maximum portability:

- **devices.csv**: Device registry
- **flows.csv**: Detailed packet flow classifications
- **hourly_stats.csv**: Aggregated statistics per hour
- **daily_stats.csv**: Daily summaries (used by stats command)

**Why CSV?** Universal compatibility with Excel, Google Sheets, Python, R, Gnuplot, and any other data analysis tool. No database dependencies required!

See [CSV_FORMAT.md](CSV_FORMAT.md) for complete file format documentation and [CSV_STORAGE.md](CSV_STORAGE.md) for analysis examples.

## Performance Considerations

- Captures only packet headers (96 bytes) to minimize overhead
- Processes data in batches to reduce CPU load
- Uses circular buffer to limit memory usage
- Automatically cleans old data when size exceeds 100MB

## Privacy & Legal Notice

This tool is intended for network administrators monitoring their own networks with proper authorization. Users must:
- Have legal authority to monitor the network
- Comply with local privacy laws
- Inform network users of monitoring activities
- Only analyze metadata, not packet contents

## Troubleshooting

**High CPU usage**: Reduce capture frequency in config
**Storage full**: Enable automatic data cleanup
**Missing traffic**: Update IP ranges for social media platforms

## License

MIT License - see LICENSE file

## Contributing

Issues and pull requests are welcome!
