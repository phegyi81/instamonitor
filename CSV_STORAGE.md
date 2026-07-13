# InstaMonitor — CSV Storage & Analysis

InstaMonitor stores all data as plain CSV files in the project's `data/`
directory. No database engine is involved — the files are the storage. This page
explains why, and shows practical ways to analyze the data.

For the exact column definitions of every file, see [CSV_FORMAT.md](CSV_FORMAT.md).

## Why CSV?

- **Universal** — opens in Excel/Sheets, imports into any database, and is
  native to pandas, R, Gnuplot, matplotlib, etc.
- **Human-readable** — inspect or edit with any text editor; easy to debug.
- **Portable** — copy with `scp`/USB; version-control friendly.
- **No dependencies** — no `sqlite3` package; pure Python with `fcntl` file
  locking for safe concurrent writes.
- **Right-sized for the workload** — the analyzer writes on the order of once
  per finished flow, so raw write throughput is irrelevant; portability and
  simplicity matter more on a small router.

Trade-off: complex ad-hoc queries need pandas or an import step. The
pre-aggregated `hourly_stats.csv` / `daily_stats.csv` cover the common reports
without any querying.

## Files at a Glance

```
data/
├── flows.csv          # one row per classified flow (most detailed)
├── hourly_stats.csv   # per-hour aggregates
├── daily_stats.csv    # per-day aggregates (read by stats.py)
├── devices.csv        # device registry
├── training_data.csv  # labeled features from label.sh (for training)
└── ip_ownership.csv   # resolved remote-IP owners (cache)
```

## Sample Data

**flows.csv** (most detailed):
```csv
timestamp,device_ip,remote_ip,platform,activity_type,duration_seconds,packet_count,bytes_up,bytes_down,avg_packet_size,packet_rate,bidirectional_ratio
2026-07-07T14:30:45,192.168.1.100,157.240.1.1,instagram,reels,45.50,250,5000,125000,500.00,5.50,0.100
```

**daily_stats.csv** (used by `stats.py`):
```csv
date,device_ip,platform,activity_type,total_duration_seconds,total_bytes,flow_count
2026-07-07,192.168.1.100,instagram,reels,45.50,130000,1
```

Value fields:
- `platform` — `instagram`, `tiktok`, or empty (kept but unattributed)
- `activity_type` — `chat` / `video_call` / `reels` / `other` / `unknown`

## Analysis Recipes

### View today's summary
```sh
./stats.py --today
# or straight from the file:
grep "$(date +%Y-%m-%d)" data/daily_stats.csv
```

### Total reels time
```sh
awk -F, '$4=="reels"{s+=$5} END{printf "%.1f hours\n", s/3600}' data/daily_stats.csv
```

### Data usage by platform
```sh
awk -F, 'NR>1{b[$3]+=$6} END{for(p in b) printf "%s: %.2f MB\n", p, b[p]/1048576}' data/daily_stats.csv
```

### Activity breakdown (duration)
```sh
awk -F, 'NR>1{d[$4]+=$5} END{for(a in d) printf "%s: %.1f h\n", a, d[a]/3600}' data/daily_stats.csv
```

### Export to your computer
```sh
scp root@router:/root/instamonitor/data/*.csv ~/Downloads/
```

### pandas
```python
import pandas as pd

daily = pd.read_csv('data/daily_stats.csv', parse_dates=['date'])
print(daily.groupby('platform')['total_bytes'].sum() / 1_048_576)     # MB per platform
print(daily.groupby('activity_type')['total_duration_seconds'].sum() / 3600)  # hours per activity

daily.groupby('date')['total_bytes'].sum().plot()   # usage over time
```

### Gnuplot
```gnuplot
set datafile separator ","
set xdata time
set timefmt "%Y-%m-%d"
set format x "%m/%d"
set ylabel "Bytes"
set title "Daily social-media usage"
plot 'data/daily_stats.csv' using 1:6 every ::1 with lines title 'Usage'
```

### Jupyter — flows over time
```python
import pandas as pd
flows = pd.read_csv('data/flows.csv', parse_dates=['timestamp'])
flows.set_index('timestamp').resample('1h')['bytes_down'].sum().plot()
```

## A Simple Usage Alert

```sh
#!/bin/sh
# Warn if today's social-media data crosses a limit. Add to cron if you like.
cd "$(dirname "$0")"
LIMIT_MB=500
TODAY=$(date +%Y-%m-%d)

USED_MB=$(awk -F, -v d="$TODAY" '$1==d{s+=$6} END{printf "%.0f", s/1048576}' data/daily_stats.csv)

[ -n "$USED_MB" ] && [ "$USED_MB" -gt "$LIMIT_MB" ] && \
  echo "Alert: social-media data today ${USED_MB}MB > ${LIMIT_MB}MB"
```

## Backups & Rotation

**Backup:**
```sh
tar -czf data/instamonitor-$(date +%Y%m%d).tar.gz data/*.csv
```

**Trim the big file** (keep the header + recent rows):
```sh
head -1 data/flows.csv > data/flows.new
tail -10000 data/flows.csv >> data/flows.new
mv data/flows.new data/flows.csv
```

**Cron backup with 30-day retention:**
```sh
0 2 * * * cd /root/instamonitor && tar -czf data/backup-$(date +\%Y\%m\%d).tar.gz data/*.csv && find data -name 'backup-*.tar.gz' -mtime +30 -delete
```

## Maintenance Notes

- **Locks:** writers use `fcntl`. If a run was killed uncleanly and you suspect a
  stale lock, stop everything (`killall run.sh tcpdump analyzer.py`) and restart.
- **Validate a file:**
  ```sh
  python3 -c "import csv,sys; list(csv.DictReader(open('data/daily_stats.csv'))); print('OK')"
  ```
- **Rebuild a truncated file** (keep header + well-formed data rows):
  ```sh
  head -1 data/flows.csv > data/flows.clean
  grep -E '^[0-9]{4}-' data/flows.csv >> data/flows.clean
  mv data/flows.clean data/flows.csv
  ```

## Data Flow

```
finished flow ─▶ flows.csv
                     │  (aggregated as flows are recorded)
                     ├─▶ hourly_stats.csv
                     └─▶ daily_stats.csv ─▶ stats.py
```

See [CSV_FORMAT.md](CSV_FORMAT.md) for the complete schema of each file.
