# InstaMonitor CSV File Format Guide

InstaMonitor stores everything as plain CSV so the data works with Excel, Google
Sheets, pandas, R, SQLite, Gnuplot, or any other tool — no database required.

## Data Directory

All files live in the project's `data/` directory (configurable via `DATA_DIR`
in `config.conf`; relative paths resolve against the config file's directory):

```
data/
├── packet_log.txt     # transient raw packet records (not CSV)
├── flows.csv          # one row per classified flow
├── hourly_stats.csv   # hourly aggregates
├── daily_stats.csv    # daily aggregates (read by stats.py)
├── devices.csv        # device registry
├── training_data.csv  # labeled feature rows produced by label.sh
└── ip_ownership.csv   # cache of resolved remote-IP owners
```

Column meanings for the value fields:

- **platform** — `instagram`, `tiktok`, or empty/`unknown` (kept but unattributed)
- **activity_type** — a trained label (`chat`, `video_call`, `reels`, `other`)
  or `unknown` (assigned when model confidence is below `CONFIDENCE_THRESHOLD`)

---

## 1. flows.csv

**Purpose:** one record per classified traffic flow.

**Columns:**
- `timestamp` — ISO 8601 time the flow was recorded
- `device_ip` — monitored LAN device IP
- `remote_ip` — remote server IP
- `platform` — `instagram` / `tiktok` / empty
- `activity_type` — `chat` / `video_call` / `reels` / `other` / `unknown`
- `duration_seconds` — flow duration (decimal)
- `packet_count` — total packets in the flow
- `bytes_up` — bytes sent (upload)
- `bytes_down` — bytes received (download)
- `avg_packet_size` — mean packet size in bytes (decimal)
- `packet_rate` — packets per second (decimal)
- `bidirectional_ratio` — how two-way the flow is (0.0–1.0)

**Example:**
```csv
timestamp,device_ip,remote_ip,platform,activity_type,duration_seconds,packet_count,bytes_up,bytes_down,avg_packet_size,packet_rate,bidirectional_ratio
2026-07-07T14:30:45,192.168.1.100,157.240.1.1,instagram,reels,45.25,387,8500,1250000,500.12,8.55,0.095
2026-07-07T14:35:12,192.168.1.100,157.240.1.1,instagram,chat,12.80,64,3200,4100,114.06,5.00,0.438
```

**pandas:**
```python
import pandas as pd
df = pd.read_csv('data/flows.csv', parse_dates=['timestamp'])
df.groupby('activity_type')['duration_seconds'].sum()
```

---

## 2. hourly_stats.csv

**Purpose:** pre-aggregated per-hour statistics.

**Columns:**
- `timestamp` — ISO 8601, rounded to the hour (`YYYY-MM-DDTHH:00:00`)
- `device_ip`
- `platform`
- `activity_type`
- `total_duration_seconds` — sum of flow durations in the hour
- `total_bytes` — sum of up + down bytes in the hour
- `flow_count` — number of flows in the hour

**Example:**
```csv
timestamp,device_ip,platform,activity_type,total_duration_seconds,total_bytes,flow_count
2026-07-07T14:00:00,192.168.1.100,instagram,reels,180.50,5250000,4
2026-07-07T14:00:00,192.168.1.100,instagram,chat,45.20,12500,8
2026-07-07T15:00:00,192.168.1.101,tiktok,reels,320.75,8900000,12
```

---

## 3. daily_stats.csv

**Purpose:** pre-aggregated per-day statistics; this is what `stats.py` reads.

**Columns:**
- `date` — `YYYY-MM-DD`
- `device_ip`
- `platform`
- `activity_type`
- `total_duration_seconds`
- `total_bytes`
- `flow_count`

**Example:**
```csv
date,device_ip,platform,activity_type,total_duration_seconds,total_bytes,flow_count
2026-07-07,192.168.1.100,instagram,reels,1825.50,25000000,45
2026-07-07,192.168.1.100,instagram,chat,245.75,125000,28
2026-07-07,192.168.1.100,tiktok,reels,980.25,18500000,32
```

---

## 4. devices.csv

**Purpose:** registry of devices seen.

**Columns:**
- `ip_address`
- `mac_address` (if available)
- `device_name` (if configured)
- `first_seen` — ISO 8601
- `last_seen` — ISO 8601

**Example:**
```csv
ip_address,mac_address,device_name,first_seen,last_seen
192.168.1.100,AA:BB:CC:DD:EE:FF,Phone,2026-07-07T10:15:30,2026-07-07T14:32:18
```

---

## 5. training_data.csv

**Purpose:** labeled feature rows produced by `label.sh` / `features.py`, used
to train the model on your laptop. **Not** written by the live monitor.

**Columns:** the 25 feature columns (in `features.py`'s canonical order)
followed by a final `label` column:

```
pkt_count, bytes_up, bytes_down, total_bytes, flow_duration,
bytes_per_sec_up, bytes_per_sec_down, pkts_per_sec,
pkt_size_mean, pkt_size_std, pkt_size_min, pkt_size_max, pkt_size_median,
pkt_size_up_mean, pkt_size_up_std, pkt_size_down_mean, pkt_size_down_std,
iat_mean, iat_std, iat_min, iat_max, iat_median,
download_ratio, bidirectional_ratio, burst_ratio, label
```

Count rows per label:
```sh
cut -d, -f26 data/training_data.csv | sort | uniq -c
```

---

## 6. ip_ownership.csv

**Purpose:** cache written by `ipinfo.py` so each remote IP is resolved only
once.

**Columns:**
- `ip`
- `platform` — `instagram` / `tiktok` / `other` / `unknown`
- `method` — how it was resolved (e.g. `rdns`, `whois`, `none`)
- `detail` — the matched hostname / evidence
- `resolved_at` — ISO 8601

**Example:**
```csv
ip,platform,method,detail,resolved_at
157.240.1.1,instagram,rdns,edge-star-mini.c10r.instagram.com,2026-07-07T14:30:45
203.0.113.7,other,rdns,rr1.sn-abc.googlevideo.com,2026-07-07T14:31:02
198.51.100.9,unknown,none,,2026-07-07T14:31:20
```

Clear it to force re-resolution: `: > data/ip_ownership.csv`

---

## Importing Into Other Tools

**SQLite:**
```sh
sqlite3 analysis.db
.mode csv
.import data/flows.csv flows
.import data/daily_stats.csv daily_stats
```

**pandas:**
```python
import pandas as pd
flows = pd.read_csv('data/flows.csv', parse_dates=['timestamp'])
daily = pd.read_csv('data/daily_stats.csv', parse_dates=['date'])
```

**R:**
```r
library(readr)
flows <- read_csv("data/flows.csv")
daily <- read_csv("data/daily_stats.csv")
```

**Gnuplot:**
```gnuplot
set datafile separator ","
set xdata time
set timefmt "%Y-%m-%d"
plot 'data/daily_stats.csv' using 1:6 with lines title 'Bytes/day'
```

## Quick Analysis Examples

Total reels time from daily stats:
```sh
awk -F, '$4=="reels"{s+=$5} END{printf "%.1f hours\n", s/3600}' data/daily_stats.csv
```

Data by platform:
```sh
awk -F, 'NR>1{b[$3]+=$6} END{for(p in b) printf "%s: %.2f MB\n", p, b[p]/1048576}' data/daily_stats.csv
```

Busiest hours:
```sh
awk -F, 'NR>1{h=substr($1,12,2); t[h]+=$6} END{for(x in t) print x, t[x]}' data/hourly_stats.csv | sort -n
```

## Backups

```sh
tar -czf instamonitor-backup-$(date +%Y%m%d).tar.gz data/*.csv
```

## Schema Stability

Columns are appended, never reordered or removed, so existing importers keep
working across versions.
