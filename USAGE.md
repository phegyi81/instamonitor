# InstaMonitor Usage Guide

## Table of Contents
1. [The Workflow at a Glance](#the-workflow-at-a-glance)
2. [Recording Training Data](#recording-training-data)
3. [Training the Model](#training-the-model)
4. [Running the Monitor](#running-the-monitor)
5. [Viewing Statistics](#viewing-statistics)
6. [Understanding Classifications](#understanding-classifications)
7. [On-the-fly IP Ownership Resolution](#on-the-fly-ip-ownership-resolution)
8. [Performance Tuning](#performance-tuning)
9. [Data Export](#data-export)
10. [Maintenance](#maintenance)

All commands assume you are in the project directory (where `run.sh` lives).
Everything runs self-contained from here; runtime data goes into `./data/`.

## The Workflow at a Glance

```
label.sh  ──▶  data/training_data.csv  ──▶  train.py (laptop)  ──▶  model.json
                                                                        │
                                                                        ▼
                              config.conf  ──▶  run.sh  ──▶  analyzer.py + model.py
                                                                        │
                                                                        ▼
                                                     data/*.csv  ──▶  stats.py
```

1. **Record** labeled sessions with `label.sh`.
2. **Train** a Random Forest on your laptop with `train.py`, producing `model.json`.
3. **Copy** `model.json` to the router.
4. **Run** `run.sh` to capture and classify live traffic.
5. **Report** with `stats.py`.

## Recording Training Data

The classifier only knows what you teach it. `label.sh` captures one device's
traffic for a fixed time and tags every resulting flow with a label.

```sh
label.sh <label> [duration_seconds] [device_ip] [interface]
```

- `label` — one of `chat`, `video_call`, `reels`, `other` (any string works)
- `duration` — seconds to record (default `300`)
- `device_ip` — LAN IP of the phone (default: first entry in `DEVICE_IPS`)
- `interface` — capture interface (default: `CAPTURE_INTERFACE`, i.e. `br-lan`)

### Good labeling practice

- Do **one pure activity at a time**, with other apps closed.
- Record a dedicated **`other`** session — normal usage with **no** Instagram or
  TikTok open — so the model learns background traffic and doesn't force it into
  a real class.
- Record several sessions per label, on different days / network conditions.
- More data ⇒ better accuracy.

```sh
./label.sh chat        300
./label.sh video_call  300
./label.sh reels       300
./label.sh other       300
```

Each run appends feature rows to `data/training_data.csv` (25 feature columns +
a final `label` column). Check your class balance:

```sh
cut -d, -f26 data/training_data.csv | sort | uniq -c
```

## Training the Model

`scikit-learn` is too heavy for the router, so training runs on your laptop and
only the tiny `model.json` goes back to the router.

```sh
# On the laptop (needs: pip install scikit-learn)
./train.py --input training_data.csv --output model.json
```

Useful options:

| Option | Default | Meaning |
|--------|---------|---------|
| `--input` | `data/training_data.csv` | Labeled dataset. |
| `--output` | `model.json` | Where to write the exported model. |
| `--trees` | `200` | Number of trees in the forest. |
| `--max-depth` | (none) | Optional depth cap. |
| `--threshold` | `0.6` | Confidence below which a flow becomes `unknown`. |
| `--test-size` | `0.25` | Hold-out fraction for the report. |
| `--seed` | `42` | Random seed for reproducibility. |

`train.py` prints a **classification report**, **confusion matrix**,
**cross-validation accuracy**, and **feature importances**. Use these to decide
whether the model is good enough before copying it to the router. If a class is
weak, record more sessions for it and retrain.

The exported `model.json` is dependency-free JSON (trees stored as plain
arrays); `model.py` on the router evaluates it with the Python standard library
only.

## Running the Monitor

```sh
# Foreground (Ctrl+C to stop and flush all pending flows)
./run.sh

# Background, logging to a file
./run.sh > data/instamonitor.log 2>&1 &

# Point at a specific config file
sh run.sh config.conf
```

`run.sh` starts `capture.sh` (tcpdump) and `analyzer.py` together and shuts both
down cleanly on Ctrl+C / TERM.

Check status:

```sh
ps | grep -E "(capture|analyzer|tcpdump)" | grep -v grep
```

Stop a background run:

```sh
killall run.sh tcpdump analyzer.py
```

### When is a flow recorded?

A flow is written once it is considered finished — after `FLOW_TIMEOUT` idle
seconds (default 60), or immediately for all open flows when you stop with
Ctrl+C. Flows with fewer than `MIN_FLOW_PACKETS` packets are ignored.

## Viewing Statistics

`stats.py` reads the aggregated `data/daily_stats.csv`.

```sh
./stats.py --today
./stats.py --yesterday
./stats.py --week
./stats.py --device 192.168.1.100 --today
./stats.py --today --export data/today.csv
```

Example:

```
Statistics for all devices
Period: 2026-07-07 to 2026-07-07

================================================================================
Platform     Activity             Duration        Data            Sessions
================================================================================
instagram    chat                 00:15:30        5.25 MB         12
instagram    reels                02:30:15        450.75 MB       8
tiktok       reels                01:45:20        380.50 MB       15
tiktok       video_call           00:25:10        125.25 MB       2
================================================================================
TOTAL                             04:56:15        961.75 MB
================================================================================
```

## Understanding Classifications

The activity classes are exactly the labels you trained with. The recommended
set and their typical traffic signatures:

### chat — messaging / DMs
- Small packets, bidirectional, sporadic timing.
- DMs, comments, story replies, quick reactions.

### video_call — live / calls
- Medium packets, steady rate, strongly bidirectional.
- Watching or joining Lives, video calls.

### reels — scrolling short video
- Large packets, mostly download, bursty as clips preload.
- Reels, TikTok feed, Stories.

### other — background traffic
- Anything the phone does that isn't Instagram/TikTok you care about.
- Present so the model has a "none of the above" class.

### unknown — low confidence
- Not a trained label. Assigned automatically when the model's top-class
  probability is below `CONFIDENCE_THRESHOLD`. Prevents confident-looking
  misclassification of traffic the model hasn't really learned.

If you see too much `unknown`: record more training data, or (carefully) lower
`CONFIDENCE_THRESHOLD` in `config.conf`.

## On-the-fly IP Ownership Resolution

Instead of maintaining lists of Instagram/TikTok IP ranges (which change
constantly and share CDNs), InstaMonitor resolves each remote IP's owner at
runtime and caches the result in `data/ip_ownership.csv`.

For every new remote IP the resolver (`ipinfo.py`) does:

1. **Reverse DNS** (and optional **whois** if `IP_FILTER_USE_WHOIS=true`).
2. Matches the hostname against known patterns:
   - Instagram/Meta (`instagram`, `fbcdn`, `facebook`, `meta`…) ⇒ tag `instagram`
   - TikTok/ByteDance (`tiktok`, `tiktokcdn`, `byteoversea`, `bytedance`,
     `muscdn`…) ⇒ tag `tiktok`
   - Clearly unrelated (`googlevideo`, `youtube`, `netflix`, `spotify`,
     `apple`, `windowsupdate`, `whatsapp`…) ⇒ mark `other`
3. Anything it can't prove — including shared CDNs like Akamai, Fastly,
   Cloudflare, Amazon — stays **unknown** and is **kept**.

Relevant `config.conf` settings:

```sh
IP_FILTER_ENABLED=true      # turn resolution on/off
DROP_CONFIRMED_OTHER=true   # drop flows proven unrelated (set false to keep all)
IP_FILTER_USE_WHOIS=false   # also consult whois (needs the 'whois' package)
IP_OWNERSHIP_CACHE=data/ip_ownership.csv
```

Design principle: it only drops a flow when it is **certain** the flow is
unrelated. Ambiguity is always resolved in favor of keeping the flow, because
Instagram/TikTok are frequently served from shared CDNs.

You can inspect or pre-warm the cache directly:

```sh
./ipinfo.py 157.240.1.1 1.2.3.4 --cache          # add --whois to also try whois
cat data/ip_ownership.csv
```

## Performance Tuning

The router is weak, so keep it light.

**Lower CPU:**
```sh
# config.conf
ANALYSIS_INTERVAL=30     # analyze less often (from 10)
SNAPSHOT_LENGTH=64       # capture fewer header bytes (from 96)
```

**Lower memory:**
```sh
# config.conf
BUFFER_SIZE=5000         # smaller capture buffer (from 10000)
FLOW_TIMEOUT=30          # evict/flush flows sooner (from 60)
```

**Keep IP resolution cheap:** leave `IP_FILTER_USE_WHOIS=false` (reverse DNS
only). Each IP is resolved once and cached, so steady-state overhead is minimal.

**Limit when it runs** with cron:
```sh
0 7  * * * /root/instamonitor/run.sh > /root/instamonitor/data/instamonitor.log 2>&1 &
0 23 * * * killall run.sh tcpdump analyzer.py
```

## Data Export

Everything is already CSV in `./data/` — copy the files anywhere:

```sh
scp root@router:/root/instamonitor/data/*.csv ~/Downloads/
```

Or use `stats.py`:

```sh
./stats.py --today --export data/today.csv
./stats.py --device 192.168.1.100 --week --export data/device_week.csv
```

Quick looks:

```sh
column -t -s, data/daily_stats.csv | less
grep instagram data/daily_stats.csv
```

See [CSV_FORMAT.md](CSV_FORMAT.md) for importing into pandas, R, SQLite,
Gnuplot, Excel, and more.

### Automated daily report

```sh
cat > daily_report.sh << 'EOF'
#!/bin/sh
cd "$(dirname "$0")"
DATE=$(date +%Y-%m-%d)
./stats.py --today > "data/report_$DATE.txt"
EOF
chmod +x daily_report.sh

echo "0 0 * * * $(pwd)/daily_report.sh" >> /etc/crontabs/root
/etc/init.d/cron restart
```

## Maintenance

- **Add training data** whenever accuracy drifts, then retrain and redeploy
  `model.json`. This is the main lever for accuracy — not editing thresholds.
- **Watch the logs** for capture or resolution errors.
- **Archive old CSV** if storage gets tight:
  ```sh
  tar -czf data/backup-$(date +%Y%m).tar.gz data/*.csv
  for f in data/flows.csv data/hourly_stats.csv; do head -1 "$f" > "$f.new" && mv "$f.new" "$f"; done
  ```
- **Refresh the IP cache** occasionally if ownership seems stale:
  ```sh
  : > data/ip_ownership.csv   # clears it; it rebuilds automatically (loses the header until next write)
  ```

## Privacy Reminder

InstaMonitor reads metadata only — no decryption, no payloads, no content.
Inform the people on your network, monitor only networks you're authorized to,
and keep data no longer than you need it.
