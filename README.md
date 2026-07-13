# InstaMonitor — Social Media Traffic Classification for OpenWrt

A lightweight, self-contained network monitor for OpenWrt routers that infers
**how** a phone is using Instagram and TikTok — chatting, video calling, or
scrolling reels — purely from **encrypted traffic metadata** (packet sizes,
timing, and direction). Nothing is decrypted; only flow statistics are used.

Classification is done by a small [**Random Forest**](https://www.ibm.com/think/topics/random-forest) model that *you* train on
*your own* labeled traffic, so it adapts to your network and devices instead of
relying on hand-guessed thresholds.

## How It Works

```
[ Phone on Wi-Fi ]
        │  (HTTPS / QUIC on port 443)
        ▼
[ OpenWrt router ]
  capture.sh ──tcpdump──▶ parse_packets.awk ──▶ data/packet_log.txt
                                                     │
  analyzer.py ◀── tails ────────────────────────────┘
     │  1. groups packets into flows (5-tuple)          features.py
     │  2. resolves each remote IP's owner (keep/drop)   ipinfo.py
     │  3. classifies the flow with the trained model    model.py + model.json
     ▼
  database.py ──▶ data/*.csv  (flows, hourly, daily)
     │
  stats.py ──▶ human-readable reports / CSV export
```

1. **Capture** — `capture.sh` runs `tcpdump` filtered to the phone's IP on
   port 443 and writes compact records (`ts|proto|src|sport|dst|dport|len`) to
   `data/packet_log.txt`.
2. **Flow assembly** — `analyzer.py` groups packets into flows keyed on the
   `(proto, local_ip, local_port, remote_ip, remote_port)` 5-tuple and computes
   ~25 statistical features (`features.py`).
3. **IP ownership** — `ipinfo.py` resolves each remote IP's owner on the fly
   (reverse DNS, optional whois), **tags** Instagram/TikTok flows and **drops**
   flows confirmed to belong to unrelated services. Ambiguous IPs are kept.
4. **Classification** — the pure-stdlib `model.py` evaluates `model.json` (a
   Random Forest exported by `train.py`) and assigns an activity label, or
   `unknown` when confidence is below a threshold.
5. **Storage & reporting** — results go to portable CSV files, viewable with
   `stats.py` or any spreadsheet/analysis tool.

## Why Machine Learning (and Why It Trains on a Laptop)

Encrypted flows can't be classified reliably with fixed size/rate cut-offs, so
InstaMonitor learns the patterns from examples **you** record. Because
`scikit-learn` is too heavy for the router, training happens on your laptop and
only a tiny dependency-free `model.json` (evaluated by `model.py`) runs on the
router.

## Components

| File | Role |
|------|------|
| `capture.sh` | Captures the phone's port-443 traffic via `tcpdump`. |
| `parse_packets.awk` | Turns `tcpdump -q` output into the 7-field packet record. |
| `analyzer.py` | Assembles flows, resolves IPs, classifies, writes to the DB. |
| `features.py` | Single source of truth for the 25 flow features (+offline CLI). |
| `model.py` | Pure-stdlib Random Forest evaluator (runs on the router). |
| `train.py` | scikit-learn trainer → `model.json` (**runs on your laptop**). |
| `ipinfo.py` | On-the-fly remote-IP ownership resolver with a local cache. |
| `label.sh` | Records one labeled session into the training dataset. |
| `database.py` | CSV storage + hourly/daily aggregation. |
| `stats.py` | Command-line reporting and CSV export. |
| `run.sh` | Launcher: starts capture + analyzer, clean shutdown on Ctrl+C. |
| `install.sh` | Installs packages and marks scripts executable. |
| `config.conf` | All configuration (device IPs, IP filter, ML settings…). |

## System Requirements

- OpenWrt 22.03+ (developed on a Netgear WNDR3700 v4, MIPS)
- `python3-light`, `python3-decimal`, `tcpdump` (installed by `install.sh`)
- A laptop with Python 3 + `scikit-learn` for training (not the router)
- A few MB of storage; everything lives in the project directory

## Installation

```sh
# 1. Copy the project to the router
scp -r instamonitor root@192.168.1.1:/root/

# 2. SSH in and run the setup (installs packages, chmod +x)
ssh root@192.168.1.1
cd /root/instamonitor
sh install.sh
```

`install.sh` copies nothing to system locations — the tool runs entirely from
its own folder and writes runtime data only to `./data/`.

## Quick Workflow

```sh
# 1. Point it at the phone you want to monitor
vi config.conf          # set DEVICE_IPS=192.168.1.100

# 2. Record labeled sessions (one pure activity at a time, ~5 min each)
./label.sh chat        300
./label.sh video_call  300
./label.sh reels       300
./label.sh other       300      # normal usage, NO Instagram/TikTok

# 3. Train ON YOUR LAPTOP (scikit-learn required)
scp data/training_data.csv features.py train.py laptop:
#   on the laptop:
pip install scikit-learn
./train.py --input training_data.csv --output model.json
#   back to the router:
scp model.json root@192.168.1.1:/root/instamonitor/

# 4. Monitor (Ctrl+C to stop)
./run.sh

# 5. View statistics
./stats.py --today
```

See [QUICKSTART.md](QUICKSTART.md) for the step-by-step version and
[USAGE.md](USAGE.md) for the full guide.

## Configuration

All settings live in `config.conf` (a plain `KEY=value` file). The most
important ones:

```sh
CAPTURE_INTERFACE=br-lan          # LAN bridge to sniff
DEVICE_IPS=192.168.1.100          # phone(s) to monitor (space-separated)

IP_FILTER_ENABLED=true            # resolve remote IP owners at runtime
DROP_CONFIRMED_OTHER=true         # drop flows proven unrelated (YouTube, etc.)
IP_FILTER_USE_WHOIS=false         # also consult whois (needs 'whois' installed)

MODEL_PATH=model.json             # trained model (falls back to heuristic if absent)
CONFIDENCE_THRESHOLD=0.6          # below this a flow is labeled "unknown"
MIN_FLOW_PACKETS=5                # ignore flows with too little signal
FLOW_TIMEOUT=60                   # idle seconds before a flow is recorded
```

Relative paths in `config.conf` are resolved against the directory containing
the config file.

## Activity Labels

The classes are simply the labels you record with `label.sh`. The recommended
set is:

- **chat** — direct messages / comments (small, bidirectional, sporadic)
- **video_call** — live / calls (steady, strongly bidirectional)
- **reels** — scrolling reels/TikToks (large, download-heavy, bursty)
- **other** — normal non-Instagram/TikTok background traffic
- **unknown** — assigned automatically when model confidence is below threshold

## Data Storage

Everything is stored as portable CSV in `./data/`:

- `flows.csv` — every classified flow
- `hourly_stats.csv` / `daily_stats.csv` — aggregates (daily is what `stats.py` reads)
- `devices.csv` — device registry
- `training_data.csv` — labeled feature rows produced by `label.sh`
- `ip_ownership.csv` — cache of resolved remote-IP owners

See [CSV_FORMAT.md](CSV_FORMAT.md) for the exact schemas and
[CSV_STORAGE.md](CSV_STORAGE.md) for analysis recipes.

## Privacy & Legal Notice

InstaMonitor inspects **metadata only** — it never decrypts TLS, reads message
content, or stores payloads. Use it only on networks you are authorized to
monitor, inform the people using the network, and comply with local privacy law
(GDPR and equivalents).

## Troubleshooting

Common issues and fixes are in [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

## License

MIT License — see [LICENSE](LICENSE).
