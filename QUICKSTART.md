# Quick Start Guide

Get InstaMonitor capturing, trained, and classifying. The one thing that makes
this different from a plain packet sniffer: **you record a little labeled
traffic first, train a model on your laptop, then let the router classify.**

## Prerequisites

- OpenWrt router (developed on 22.03) with SSH access
- The phone whose Instagram/TikTok usage you want to classify, on your Wi-Fi
- A laptop with Python 3 and internet (for `pip install scikit-learn`)
- A few MB of free space on the router

## Step 1 — Copy the project to the router

From your computer, inside the `instamonitor` directory:

```sh
# Replace 192.168.1.1 with your router's IP
scp -r . root@192.168.1.1:/root/instamonitor/
```

## Step 2 — SSH in and install

```sh
ssh root@192.168.1.1
cd /root/instamonitor
sh install.sh
```

`install.sh` runs `opkg update`, installs `python3-light`, `python3-decimal`,
and `tcpdump`, and marks the scripts executable. Everything runs from this
directory — nothing is written to `/etc`, `/var`, or `/tmp`.

## Step 3 — Tell it which phone to watch

```sh
vi config.conf
```

Set at least:

```sh
CAPTURE_INTERFACE=br-lan          # usually the LAN bridge
DEVICE_IPS=192.168.1.100          # the phone's LAN IP
```

Give the phone a static DHCP lease so its IP doesn't change.

## Step 4 — Record labeled training sessions

Do **one pure activity at a time**, with other apps closed, so the labels stay
clean. Five minutes each is a good start; record more later to improve accuracy.

```sh
./label.sh chat        300      # spend 5 min only chatting / DMs
./label.sh video_call  300      # spend 5 min on a live / video call
./label.sh reels       300      # spend 5 min only scrolling reels/TikToks
./label.sh other       300      # normal usage with NO Instagram/TikTok open
```

Each run appends feature rows (tagged with the label) to
`data/training_data.csv`. The `other` session is important — it teaches the
model what background traffic looks like so it isn't forced into a real class.

Check what you've collected:

```sh
cut -d, -f26 data/training_data.csv | sort | uniq -c   # counts per label
```

## Step 5 — Train the model (on your laptop)

`scikit-learn` is too heavy for the router, so train on your laptop and copy
back only the small `model.json`.

```sh
# On the laptop:
scp root@192.168.1.1:/root/instamonitor/data/training_data.csv .
scp root@192.168.1.1:/root/instamonitor/features.py .
scp root@192.168.1.1:/root/instamonitor/train.py .

pip install scikit-learn
./train.py --input training_data.csv --output model.json

# Copy the trained model back to the router:
scp model.json root@192.168.1.1:/root/instamonitor/
```

`train.py` prints a classification report, confusion matrix, cross-validation
accuracy, and feature importances so you can judge quality before deploying.

## Step 6 — Start monitoring

```sh
# Foreground (Ctrl+C to stop)
./run.sh

# Or background, logging to a file
./run.sh > data/instamonitor.log 2>&1 &
```

Confirm it's running:

```sh
ps | grep -E "(capture|analyzer|tcpdump)" | grep -v grep
```

You should see `capture.sh`, `analyzer.py`, and `tcpdump`.

## Step 7 — Generate some traffic and check the stats

1. Use Instagram/TikTok on the monitored phone for a minute or two.
2. Wait for flows to finish (a flow is recorded after `FLOW_TIMEOUT` idle
   seconds, default 60), or stop with Ctrl+C to flush everything.
3. View the results:

```sh
./stats.py --today
```

### Example output

```
Statistics for all devices
Period: 2026-07-07 to 2026-07-07

================================================================================
Platform     Activity             Duration        Data            Sessions
================================================================================
instagram    reels                00:02:30        45.75 MB        1
tiktok       reels                00:01:45        38.50 MB        1
instagram    chat                 00:00:40        0.12 MB         3
================================================================================
TOTAL                             00:04:55        84.37 MB
================================================================================
```

## Running Without a Model

If `model.json` isn't present yet, the analyzer falls back to a simple built-in
heuristic so you still get *something* — but the whole point is the trained
model, so record data and train as soon as you can.

## Quick Troubleshooting

**Nothing captured?** Check the interface name and that the phone's IP matches:

```sh
ifconfig                       # find the LAN bridge (often br-lan)
tcpdump -i br-lan -c 10 -n     # confirm you see traffic
```

**Everything classified `unknown`?** Either there's no `model.json`, the model
needs more/better training data, or `CONFIDENCE_THRESHOLD` is too high. Record
more labeled sessions and retrain.

**Flows dropped unexpectedly?** `DROP_CONFIRMED_OTHER=true` removes flows proven
unrelated to Instagram/TikTok. Set it to `false` in `config.conf` to keep
everything while you debug.

More in [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

## Useful Commands

```sh
./run.sh                                   # start (foreground)
killall run.sh tcpdump analyzer.py         # stop a background run
./stats.py --today                         # today's summary
./stats.py --device 192.168.1.100 --week   # one device, this week
./stats.py --today --export data/today.csv # export a report
tail -f data/instamonitor.log              # watch a background run
./label.sh reels 300                       # add more training data
```

## Next Steps

- **[USAGE.md](USAGE.md)** — full guide: monitoring, stats, tuning, exporting
- **[CSV_FORMAT.md](CSV_FORMAT.md)** — exact CSV schemas
- **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)** — problem solving
- **[PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md)** — architecture and design

Record more labeled data over time and retrain — that's what steadily improves
accuracy.
