# InstaMonitor CSV File Format Guide

InstaMonitor stores all data in simple CSV files for maximum portability and ease of analysis. These files can be opened in Excel, Google Sheets, imported into databases, or processed with tools like Gnuplot, Python pandas, R, or any other data analysis tool.

## Data Directory Structure

All CSV files are stored in `/var/lib/instamonitor/` (configurable):

```
/var/lib/instamonitor/
├── devices.csv          # Device registry
├── flows.csv            # Detailed flow-level data
├── hourly_stats.csv     # Hourly aggregated statistics
└── daily_stats.csv      # Daily aggregated statistics
```

## File Formats

### 1. devices.csv

**Purpose:** Registry of all devices seen on the network

**Columns:**
- `ip_address` - Device IP address (unique identifier)
- `mac_address` - MAC address (if available)
- `device_name` - Friendly name (if configured)
- `first_seen` - ISO 8601 timestamp when first detected
- `last_seen` - ISO 8601 timestamp of last activity

**Example:**
```csv
ip_address,mac_address,device_name,first_seen,last_seen
192.168.1.100,AA:BB:CC:DD:EE:FF,Johns Phone,2026-07-02T10:15:30,2026-07-02T14:32:18
192.168.1.101,11:22:33:44:55:66,Marias iPad,2026-07-02T08:22:15,2026-07-02T16:45:22
```

**Use cases:**
- Device tracking and identification
- Network inventory
- Activity timeline per device

---

### 2. flows.csv

**Purpose:** Detailed record of every classified traffic flow

**Columns:**
- `timestamp` - ISO 8601 timestamp when flow was recorded
- `device_ip` - Local device IP address
- `remote_ip` - Remote server IP address
- `platform` - Platform identifier (instagram/tiktok) or empty
- `activity_type` - Classification: chat, video_conference, video_scroll, unknown
- `duration_seconds` - How long the flow lasted (decimal)
- `packet_count` - Total number of packets in the flow
- `bytes_up` - Bytes sent (upload)
- `bytes_down` - Bytes received (download)
- `avg_packet_size` - Average packet size in bytes (decimal)
- `packet_rate` - Packets per second (decimal)
- `bidirectional_ratio` - Ratio of traffic in both directions (0.0-1.0)

**Example:**
```csv
timestamp,device_ip,remote_ip,platform,activity_type,duration_seconds,packet_count,bytes_up,bytes_down,avg_packet_size,packet_rate,bidirectional_ratio
2026-07-02T14:30:45,192.168.1.100,157.240.1.1,instagram,video_scroll,45.25,387,8500,1250000,500.12,8.55,0.095
2026-07-02T14:35:12,192.168.1.100,157.240.1.1,instagram,chat,12.80,64,3200,4100,114.06,5.00,0.438
```

**Use cases:**
- Detailed traffic analysis
- Pattern discovery
- Training machine learning models
- Debugging classification accuracy
- Export for visualization tools

**Processing examples:**

**Python (pandas):**
```python
import pandas as pd
df = pd.read_csv('flows.csv')
df['timestamp'] = pd.to_datetime(df['timestamp'])
df.groupby('activity_type')['duration_seconds'].sum()
```

**Excel:**
- Open flows.csv in Excel
- Create pivot tables by activity_type
- Chart data usage over time

**Gnuplot:**
```gnuplot
set datafile separator ","
set xdata time
set timefmt "%Y-%m-%dT%H:%M:%S"
plot 'flows.csv' using 1:9 with lines title 'Download Traffic'
```

---

### 3. hourly_stats.csv

**Purpose:** Pre-aggregated statistics per hour (for faster reporting)

**Columns:**
- `timestamp` - ISO 8601 timestamp (rounded to hour: YYYY-MM-DDTHH:00:00)
- `device_ip` - Local device IP address
- `platform` - Platform identifier (instagram/tiktok/unknown)
- `activity_type` - Classification type
- `total_duration_seconds` - Sum of all flow durations in this hour (decimal)
- `total_bytes` - Sum of all bytes (up + down) in this hour
- `flow_count` - Number of flows in this hour

**Example:**
```csv
timestamp,device_ip,platform,activity_type,total_duration_seconds,total_bytes,flow_count
2026-07-02T14:00:00,192.168.1.100,instagram,video_scroll,180.50,5250000,4
2026-07-02T14:00:00,192.168.1.100,instagram,chat,45.20,12500,8
2026-07-02T15:00:00,192.168.1.101,tiktok,video_scroll,320.75,8900000,12
```

**Use cases:**
- Quick hourly breakdowns
- Time-of-day usage patterns
- Comparing activity across hours
- Lighter weight than flows.csv

**Processing examples:**

**Generate hourly chart in Excel:**
1. Open hourly_stats.csv
2. Create pivot table: Rows=timestamp, Columns=activity_type, Values=total_bytes
3. Insert line chart

**SQL analysis (if imported to database):**
```sql
SELECT 
    strftime('%H', timestamp) as hour,
    SUM(total_bytes) as total_bytes
FROM hourly_stats
WHERE activity_type = 'video_scroll'
GROUP BY hour
ORDER BY hour;
```

---

### 4. daily_stats.csv

**Purpose:** Pre-aggregated statistics per day (for summary reports)

**Columns:**
- `date` - ISO 8601 date (YYYY-MM-DD)
- `device_ip` - Local device IP address
- `platform` - Platform identifier (instagram/tiktok/unknown)
- `activity_type` - Classification type
- `total_duration_seconds` - Sum of all flow durations for this day (decimal)
- `total_bytes` - Sum of all bytes (up + down) for this day
- `flow_count` - Number of flows for this day

**Example:**
```csv
date,device_ip,platform,activity_type,total_duration_seconds,total_bytes,flow_count
2026-07-02,192.168.1.100,instagram,video_scroll,1825.50,25000000,45
2026-07-02,192.168.1.100,instagram,chat,245.75,125000,28
2026-07-02,192.168.1.100,tiktok,video_scroll,980.25,18500000,32
2026-07-01,192.168.1.100,instagram,video_scroll,2105.80,31000000,52
```

**Use cases:**
- Daily usage summaries
- Week/month/year comparisons
- Trend analysis
- Reporting to parents/managers
- The `instamonitor-stats` command reads this file

**Processing examples:**

**Generate weekly summary:**
```python
import pandas as pd
df = pd.read_csv('daily_stats.csv')
df['date'] = pd.to_datetime(df['date'])
weekly = df.groupby([pd.Grouper(key='date', freq='W'), 'activity_type'])['total_bytes'].sum()
print(weekly)
```

**Chart in Google Sheets:**
1. Import daily_stats.csv
2. Create chart: X-axis=date, Y-axis=total_bytes, Series=activity_type
3. Choose stacked area chart

---

## Data Flow

```
[Packet Capture] 
    ↓
[flows.csv] ← Raw flow data saved immediately
    ↓
[Hourly Aggregation] ← Updated every hour
    ↓
[hourly_stats.csv]
    ↓
[Daily Aggregation] ← Updated every day
    ↓
[daily_stats.csv] ← Used by instamonitor-stats
```

## File Sizes

Typical file sizes for a household with 5 devices:

- **devices.csv**: < 1 KB (grows very slowly)
- **flows.csv**: ~500 KB - 2 MB per day (depends on activity)
- **hourly_stats.csv**: ~20-50 KB per day
- **daily_stats.csv**: ~1-2 KB per day

With automatic cleanup enabled (30 days default), total storage: **15-60 MB**

## Importing Into Other Tools

### Excel / Google Sheets
1. File → Import → CSV
2. Select delimiter: comma
3. Ensure timestamp columns are parsed as dates

### SQLite
```bash
sqlite3 analysis.db
.mode csv
.import devices.csv devices
.import flows.csv flows
.import daily_stats.csv daily_stats
```

### Python pandas
```python
import pandas as pd

devices = pd.read_csv('/var/lib/instamonitor/devices.csv')
flows = pd.read_csv('/var/lib/instamonitor/flows.csv', 
                    parse_dates=['timestamp'])
daily = pd.read_csv('/var/lib/instamonitor/daily_stats.csv',
                   parse_dates=['date'])
```

### R
```r
library(readr)
flows <- read_csv("/var/lib/instamonitor/flows.csv")
daily <- read_csv("/var/lib/instamonitor/daily_stats.csv")
```

### Gnuplot
```gnuplot
set datafile separator ","
set xlabel "Time"
set ylabel "Bytes"
set xdata time
set timefmt "%Y-%m-%d"
plot 'daily_stats.csv' using 1:6 with lines
```

## Analysis Examples

### Most Active Hours
```bash
# Using awk
awk -F, 'NR>1 {hour=substr($1,12,2); total[hour]+=$6} END {for(h in total) print h, total[h]}' hourly_stats.csv | sort -n
```

### Total Data by Platform
```bash
# Using awk
awk -F, 'NR>1 {platform[$3]+=$6} END {for(p in platform) print p, platform[p]}' daily_stats.csv
```

### Activity Breakdown
```bash
# Using awk
awk -F, 'NR>1 {activity[$4]+=$5} END {for(a in activity) printf "%s: %.1f hours\n", a, activity[a]/3600}' daily_stats.csv
```

## Best Practices

1. **Regular Backups**: CSV files are plain text - easy to backup
   ```bash
   tar -czf instamonitor-backup-$(date +%Y%m%d).tar.gz /var/lib/instamonitor/
   ```

2. **Version Control**: Track changes over time
   ```bash
   git add /var/lib/instamonitor/*.csv
   git commit -m "Daily stats $(date +%Y-%m-%d)"
   ```

3. **Archiving**: Compress old data
   ```bash
   gzip /var/lib/instamonitor/flows-2026-06.csv
   ```

4. **Export for Analysis**: Copy to your computer
   ```bash
   scp root@router:/var/lib/instamonitor/*.csv ~/data/
   ```

## Schema Stability

The CSV format is stable and backward compatible. New columns may be added in future versions but will always be appended to the right, never inserted in the middle. Existing columns will not change format or meaning.

## Advantages of CSV Format

✅ **Universal compatibility** - Works with Excel, Google Sheets, databases, programming languages  
✅ **Human readable** - Can view/edit with any text editor  
✅ **Easy to backup** - Simple file copy  
✅ **No dependencies** - No need for SQLite or other databases  
✅ **Portable** - Transfer between systems easily  
✅ **Version control friendly** - Works with git  
✅ **Tool agnostic** - Use any analysis tool you prefer  
✅ **Simple** - No complex queries needed for basic analysis  
✅ **Lightweight** - Smaller than many database formats  
✅ **Debuggable** - Easy to inspect and validate data  

Perfect for a router-based monitoring system where simplicity and portability are key!
