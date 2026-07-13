# InstaMonitor — Project Overview

## What is InstaMonitor?

InstaMonitor is a lightweight, self-contained network monitor for OpenWrt
routers. It infers **how** a phone is using Instagram and TikTok — chatting,
video calling, or scrolling reels — from **encrypted traffic metadata** alone
(packet sizes, timing, direction). Nothing is decrypted.

Classification is done by a **supervised Random Forest** that you train on your
own labeled traffic. This replaced an earlier hand-tuned threshold approach that
couldn't reliably separate the activities on encrypted flows.

## Design Principles

- **Metadata only** — never decrypt, never read content, never store payloads.
- **Self-contained** — everything runs from the project directory; runtime data
  goes only into `./data/`; nothing is written to `/etc`, `/var`, or `/tmp`.
- **Router-light** — the router never runs `scikit-learn`; it only evaluates a
  tiny dependency-free `model.json` with the Python standard library.
- **Learn, don't guess** — accuracy comes from labeled data + retraining, not
  from hand-tuned size/rate cut-offs.
- **Keep-when-unsure** — the runtime IP filter only drops flows it can *prove*
  are unrelated; ambiguous flows are always kept.

## Architecture

```
[ Phone on Wi-Fi ]
        │  HTTPS / QUIC (port 443)
        ▼
[ OpenWrt router ]
                      ┌──────────────────────── training path (offline) ─────────────────────────┐
   capture.sh         │  label.sh ─▶ features.py ─▶ data/training_data.csv                        │
      │  tcpdump       │        (copy to laptop)  ─▶ train.py + scikit-learn ─▶ model.json         │
      ▼               └────────────────────────────────────────────────────────────┬─────────────┘
   parse_packets.awk                                                                │ (copy back)
      │  ts|proto|src|sport|dst|dport|len                                           ▼
      ▼                                                              ┌──────────────────────────┐
   data/packet_log.txt ──tail──▶ analyzer.py ──▶ classify ─────────▶│ model.py reads model.json│
                                     │  features.py (25 features)    └──────────────────────────┘
                                     │  ipinfo.py (keep/drop + tag)
                                     ▼
                                  database.py ──▶ data/*.csv ──▶ stats.py
```

## Components

### Capture
- **`capture.sh`** — runs `tcpdump` on `CAPTURE_INTERFACE`, filtered to the
  monitored phone(s) (`DEVICE_IPS`) on TCP/UDP port 443, and pipes the output
  through the parser. Captures only short headers (`SNAPSHOT_LENGTH`, default
  96 bytes).
- **`parse_packets.awk`** — converts `tcpdump -q` lines into the 7-field record
  `epoch_ts|proto|src_ip|src_port|dst_ip|dst_port|length`. Skips IPv6 and ARP.

### Flow assembly & features
- **`features.py`** — the single source of truth for the **25** flow features
  (packet counts/sizes, per-direction size stats, inter-arrival timing stats,
  download ratio, bidirectional ratio, burst ratio, …). Provides `Flow`,
  `FlowTable`, packet parsing, the 5-tuple flow key, and an offline extraction
  CLI used by `label.sh`.
- **`analyzer.py`** — tails `data/packet_log.txt`, assembles flows keyed on
  `(proto, local_ip, local_port, remote_ip, remote_port)`, resolves remote-IP
  ownership, classifies each finished flow, and records it via `database.py`.

### Classification
- **`model.py`** — pure-stdlib Random Forest evaluator. Loads `model.json`,
  averages per-tree leaf distributions (soft voting), and returns
  `(label, confidence)` — or `unknown` when confidence is below the threshold.
- **`train.py`** — **laptop-only** scikit-learn trainer. Trains a
  `RandomForestClassifier` (`class_weight='balanced'`) and exports the trees to
  dependency-free `model.json`. Prints report, confusion matrix, CV accuracy,
  and feature importances.

### IP ownership
- **`ipinfo.py`** — resolves each remote IP's owner at runtime via reverse DNS
  (and optional whois), classifies it as `instagram` / `tiktok` / `other` /
  `unknown`, and caches results in `data/ip_ownership.csv`. Deliberately leaves
  shared CDNs (Akamai/Fastly/Cloudflare/Amazon) as `unknown` so their flows are
  kept.

### Labeling, storage, reporting, orchestration
- **`label.sh`** — records one labeled session into `data/training_data.csv`.
- **`database.py`** — CSV storage with hourly/daily aggregation and `fcntl`
  file locking.
- **`stats.py`** — command-line reporting and CSV export (reads
  `data/daily_stats.csv`).
- **`run.sh`** — launcher that starts capture + analyzer and shuts both down
  cleanly.
- **`install.sh`** — installs packages and marks scripts executable.
- **`config.conf`** — all configuration.

## Classification Pipeline (per flow)

1. Skip if the flow has fewer than `MIN_FLOW_PACKETS` packets.
2. Resolve the remote IP's owner (`ipinfo.py`):
   - If `DROP_CONFIRMED_OTHER` and the owner is a confirmed unrelated service →
     **drop** the flow.
   - If the owner is Instagram or TikTok → set that as the flow's platform.
   - Otherwise keep the flow with an unknown platform.
3. Compute the 25 features and run `model.py`:
   - Return the model's label if confidence ≥ `CONFIDENCE_THRESHOLD`.
   - Otherwise label the flow `unknown`.
   - If no `model.json` exists, fall back to a simple built-in heuristic.
4. Record the flow (platform + activity) via `database.py`.

## File Structure

```
instamonitor/
├── README.md              # Overview and quick workflow
├── QUICKSTART.md          # Step-by-step setup
├── USAGE.md               # Full usage guide
├── TROUBLESHOOTING.md     # Problem solving
├── PROJECT_OVERVIEW.md    # This document
├── CSV_FORMAT.md          # CSV schemas
├── CSV_STORAGE.md         # CSV analysis recipes
├── LICENSE                # MIT license
├── config.conf            # Configuration (KEY=value)
├── capture.sh             # Packet capture (tcpdump)
├── parse_packets.awk      # tcpdump → 7-field record parser
├── analyzer.py            # Flow assembly + classification
├── features.py            # 25-feature extractor (+ offline CLI)
├── model.py               # Pure-stdlib Random Forest evaluator (router)
├── train.py               # scikit-learn trainer (laptop) → model.json
├── ipinfo.py              # Runtime IP ownership resolver + cache
├── label.sh               # Labeled-session recorder
├── database.py            # CSV storage + aggregation
├── stats.py               # Reporting / export
├── run.sh                 # Launcher
├── install.sh             # Setup
└── data/                  # Runtime data (created at runtime)
    ├── packet_log.txt     # Transient packet records
    ├── flows.csv          # Classified flows
    ├── hourly_stats.csv   # Hourly aggregates
    ├── daily_stats.csv    # Daily aggregates (read by stats.py)
    ├── devices.csv        # Device registry
    ├── training_data.csv  # Labeled features from label.sh
    └── ip_ownership.csv   # Resolved remote-IP owners (cache)
```

Note: `model.json` is produced by `train.py` on your laptop and copied into the
project directory; it isn't shipped in the repo.

## Runtime Data Format

**Packet log** (`data/packet_log.txt`), one record per line:

```
epoch_ts|proto|src_ip|src_port|dst_ip|dst_port|length
```

**Flow key:** `(proto, local_ip, local_port, remote_ip, remote_port)`, normalized
so the LAN endpoint is "local" (detected via the private ranges `192.168.`,
`10.`, `172.16–31.`).

## Performance Characteristics

Developed on a Netgear WNDR3700 v4 (MIPS, modest CPU):

- Captures only short headers (default 96 bytes).
- Each remote IP is resolved once and cached, so IP resolution overhead is
  negligible in steady state.
- The router evaluates a compact JSON forest — no heavy ML runtime.
- Tunables (`ANALYSIS_INTERVAL`, `SNAPSHOT_LENGTH`, `BUFFER_SIZE`,
  `FLOW_TIMEOUT`) let you trade freshness for load.

## Privacy & Legal

**Does:** analyze packet metadata (size, timing, direction), record connection
endpoints, measure data usage and session duration, classify activity patterns.

**Does not:** decrypt TLS/HTTPS, read message content, capture credentials,
store payloads, or perform any man-in-the-middle.

**Requirements:** authorization to monitor the network, user notification (as
required by jurisdiction), and compliance with local privacy law (e.g. GDPR).

## Limitations

- Accuracy depends entirely on the quality and coverage of your training data —
  record varied sessions and retrain.
- VPN/proxy tunnels can't be classified (endpoints and patterns are hidden).
- Shared CDNs make platform attribution imperfect; such flows are kept but may
  carry an unknown platform.
- Very short flows (< `MIN_FLOW_PACKETS`) are ignored by design.

## License

MIT License — see [LICENSE](LICENSE).
