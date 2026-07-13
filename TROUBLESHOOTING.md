# InstaMonitor Troubleshooting Guide

All paths are relative to the project directory (where `run.sh` lives).
Runtime data is in `./data/`. Nothing is installed to `/etc`, `/var`, or `/tmp`.

## Table of Contents
1. [Won't Start](#wont-start)
2. [Nothing Being Captured](#nothing-being-captured)
3. [No Classifications / Everything "unknown"](#no-classifications--everything-unknown)
4. [Flows Being Dropped](#flows-being-dropped)
5. [Training Problems](#training-problems)
6. [IP Resolution Problems](#ip-resolution-problems)
7. [Performance Issues](#performance-issues)
8. [CSV / Storage Issues](#csv--storage-issues)
9. [Diagnostic Snapshot](#diagnostic-snapshot)

---

## Won't Start

**Symptoms:** `run.sh` exits immediately or no processes stay running.

**Diagnose** — run in the foreground to see errors:
```sh
./run.sh
ps | grep -E "(capture|analyzer|tcpdump)" | grep -v grep
```

**Fixes:**

1. Dependencies present?
   ```sh
   opkg list-installed | grep -E "(python3-light|python3-decimal|tcpdump)"
   opkg update && opkg install python3-light python3-decimal tcpdump
   ```
2. `statistics` import fails? You're missing `python3-decimal`:
   ```sh
   opkg install python3-decimal
   ```
3. Scripts executable?
   ```sh
   sh install.sh          # re-runs the chmod step
   ```
4. Config readable and valid?
   ```sh
   sh -n capture.sh       # shell syntax check
   cat config.conf
   ```

---

## Nothing Being Captured

**Symptoms:** `data/packet_log.txt` is empty or not growing.

**Diagnose:**
```sh
ps | grep tcpdump
tcpdump -i br-lan -c 10 -n            # do you see any traffic at all?
ls -lh data/packet_log.txt
tail data/packet_log.txt
```

**Fixes:**

1. **Wrong interface.** Find the LAN bridge and update `CAPTURE_INTERFACE`:
   ```sh
   ifconfig                            # commonly br-lan
   vi config.conf                      # set CAPTURE_INTERFACE=...
   ```
2. **Wrong device IP.** `DEVICE_IPS` must list the phone's actual LAN IP. Give
   the phone a static DHCP lease so it doesn't change:
   ```sh
   vi config.conf                      # DEVICE_IPS=192.168.1.100
   ```
3. **Confirm the phone's traffic reaches the router** (test the exact filter):
   ```sh
   tcpdump -i br-lan "host 192.168.1.100 and (tcp port 443 or udp port 443)" -c 20 -n
   ```
4. **Parser producing nothing?** Feed a sample through the awk parser:
   ```sh
   tcpdump -i br-lan -q "host 192.168.1.100 and port 443" -c 20 | awk -f parse_packets.awk
   ```
   Expected line format: `epoch_ts|proto|src_ip|src_port|dst_ip|dst_port|length`.

---

## No Classifications / Everything "unknown"

**Symptoms:** the analyzer runs but every flow is `unknown` (or you get no rows).

The number one cause is **no trained model** or **too little training data**.

**Fixes:**

1. **Is there a model?**
   ```sh
   ls -l model.json
   ```
   If missing, the analyzer uses only a crude built-in heuristic. Record data and
   train (see [Training Problems](#training-problems)).
2. **Confidence threshold too high.** Flows below `CONFIDENCE_THRESHOLD` are
   labeled `unknown`. Lower it a bit (carefully):
   ```sh
   vi config.conf                      # e.g. CONFIDENCE_THRESHOLD=0.5
   ```
3. **Not enough / unbalanced training data.** Check your class counts and record
   more of the weak ones, then retrain:
   ```sh
   cut -d, -f26 data/training_data.csv | sort | uniq -c
   ```
4. **Flows too short.** Flows with fewer than `MIN_FLOW_PACKETS` packets are
   ignored, and a flow is only recorded after `FLOW_TIMEOUT` idle seconds (or on
   Ctrl+C). Generate sustained traffic, then wait or stop to flush.
5. **Verify the packet log has data** in the expected 7-field format:
   ```sh
   head -5 data/packet_log.txt
   ```

---

## Flows Being Dropped

**Symptoms:** you clearly used Instagram/TikTok but far fewer flows are recorded
than expected.

**Cause:** `DROP_CONFIRMED_OTHER=true` discards flows whose remote IP is proven
to belong to an unrelated service. Occasionally a legitimately relevant flow
could be mis-attributed.

**Fixes:**

1. **Keep everything while debugging:**
   ```sh
   vi config.conf                      # DROP_CONFIRMED_OTHER=false
   ```
2. **Inspect what was resolved** and why a flow was dropped:
   ```sh
   cat data/ip_ownership.csv
   ```
3. **Disable resolution entirely** (keep all flows, no platform tagging):
   ```sh
   vi config.conf                      # IP_FILTER_ENABLED=false
   ```

---

## Training Problems

Training runs on your **laptop**, not the router.

**`train.py` fails: `No module named sklearn`**
```sh
pip install scikit-learn
```
(The router intentionally does **not** have scikit-learn.)

**Poor accuracy / confusing report:**
- Record more sessions, especially for the weakest class in the confusion matrix.
- Make each session a **single pure activity** with other apps closed.
- Always include an **`other`** session (no Instagram/TikTok) so the model has a
  background class.
- Retrain and copy the new `model.json` back to the router.

**Feature mismatch / weird errors:** make sure the `features.py` you train with
matches the one on the router (copy both together with `train.py`).

**Deploying the model:**
```sh
scp model.json root@router:/root/instamonitor/
```
No restart of training is needed on the router; just make sure `MODEL_PATH`
points at the file (default `model.json`).

---

## IP Resolution Problems

**Reverse DNS returns nothing / everything is `unknown`:** many IPs have no PTR
record. Those flows are **kept** (that's intended). To improve attribution, try
enabling whois:
```sh
opkg install whois
vi config.conf                        # IP_FILTER_USE_WHOIS=true
```

**Test the resolver directly:**
```sh
./ipinfo.py 157.240.1.1 8.8.8.8 --whois
```

**Stale cache:** clear it to force re-resolution:
```sh
: > data/ip_ownership.csv
```

**No internet / DNS on the router:** resolution will fail and all flows stay
`unknown` (and are kept). Fix the router's DNS, or set `IP_FILTER_ENABLED=false`.

---

## Performance Issues

**High CPU:**
```sh
top -b -n 1 | grep -E "(capture|analyzer|tcpdump)"
```
```sh
# config.conf
ANALYSIS_INTERVAL=30      # from 10
SNAPSHOT_LENGTH=64        # from 96
IP_FILTER_USE_WHOIS=false # reverse DNS only (whois is slower)
```
Or run only part of the day with cron:
```sh
0 7  * * * /root/instamonitor/run.sh > /root/instamonitor/data/instamonitor.log 2>&1 &
0 23 * * * killall run.sh tcpdump analyzer.py
```

**High memory:**
```sh
# config.conf
BUFFER_SIZE=5000          # from 10000
FLOW_TIMEOUT=30           # from 60 (flush flows sooner)
```

**Storage filling up:**
```sh
# config.conf
AUTO_CLEANUP_ENABLED=true
MAX_STORAGE_MB=50
```
Manual trim:
```sh
tar -czf data/backup-$(date +%Y%m).tar.gz data/*.csv
head -1 data/flows.csv > data/flows.new && tail -10000 data/flows.csv >> data/flows.new && mv data/flows.new data/flows.csv
```

---

## CSV / Storage Issues

**Validate a file:**
```sh
python3 -c "import csv; list(csv.DictReader(open('data/daily_stats.csv'))); print('OK')"
```

**Rebuild a truncated file** (keep header + valid rows):
```sh
head -1 data/flows.csv > data/flows.clean
grep -E '^[0-9]{4}-' data/flows.csv >> data/flows.clean
mv data/flows.clean data/flows.csv
```

**Suspected stale lock:** stop everything and restart:
```sh
killall run.sh tcpdump analyzer.py
./run.sh
```

---

## Diagnostic Snapshot

Run this from the project directory to gather the essentials:

```sh
#!/bin/sh
cd "$(dirname "$0")"
echo "=== System ===";        uname -a; uptime
echo "=== Packages ===";      opkg list-installed | grep -E "(python3-light|python3-decimal|tcpdump|whois)"
echo "=== Processes ===";     ps | grep -E "(capture|analyzer|tcpdump)" | grep -v grep || echo "not running"
echo "=== Config ===";        cat config.conf
echo "=== Model ===";         ls -l model.json 2>/dev/null || echo "no model.json (heuristic fallback)"
echo "=== Training rows ===";  [ -f data/training_data.csv ] && cut -d, -f26 data/training_data.csv | sort | uniq -c
echo "=== Data files ===";    ls -lh data/*.csv 2>/dev/null || echo "no CSV yet"
echo "=== Packet log ===";    [ -f data/packet_log.txt ] && { wc -l data/packet_log.txt; head -3 data/packet_log.txt; } || echo "none"
echo "=== IP cache ===";      [ -f data/ip_ownership.csv ] && tail -5 data/ip_ownership.csv
echo "=== Interfaces ===";    ifconfig | grep -E "^[a-z]|inet addr"
```
