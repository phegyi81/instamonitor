#!/usr/bin/env python3
"""
InstaMonitor Traffic Analyzer
=============================

Tails the packet log produced by capture.sh, groups packets into flows using
the shared feature extractor (features.py), classifies each finished flow with
the trained Random Forest (model.py / model.json), and records the result via
the CSV storage layer (database.py).

If no model.json is present it falls back to a simple heuristic so the system
still runs, but the intended path is: label.sh -> train.py -> model.json.

Usage: analyzer.py <config_file> <packet_log>
"""

import sys
import os
import time
import configparser
from collections import defaultdict
from datetime import datetime

# Local modules (same directory).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import features
import model as model_mod
import ipinfo


def read_config(config_file):
    """Parse the shell-style KEY=value config with configparser.

    The file is also sourced by the shell scripts, so it has no INI section
    header. We inject a synthetic [DEFAULT] section in memory and honor inline
    '#' comments so values like "0.6  # note" parse.
    """
    parser = configparser.ConfigParser(inline_comment_prefixes=('#',))
    with open(config_file) as f:
        parser.read_string('[DEFAULT]\n' + f.read())
    return parser


def resolve_against(config_file, path):
    """Resolve a possibly-relative path against the config file's directory."""
    if os.path.isabs(path):
        return path
    return os.path.join(os.path.dirname(os.path.abspath(config_file)), path)


def heuristic_classify(fd):
    """Fallback classifier used only when no trained model is available.

    fd is a feature name -> value dict. Returns (label, confidence).
    """
    size = fd['pkt_size_mean']
    pps = fd['pkts_per_sec']
    bidir = fd['bidirectional_ratio']
    dl = fd['download_ratio']

    if size < 300 and bidir > 0.2 and pps > 0:
        return 'chat', 0.5
    if bidir >= 0.3 and 300 <= size <= 1200 and pps >= 5:
        return 'video_call', 0.5
    if dl >= 0.7 and size >= 800:
        return 'reels', 0.5
    return model_mod.UNKNOWN_LABEL, 0.0


def main():
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <config_file> <packet_log>")
        sys.exit(1)

    config_file = sys.argv[1]
    packet_log = sys.argv[2]

    config = read_config(config_file)

    def cget(key, fallback):
        return config.get('DEFAULT', key, fallback=fallback)

    data_dir = resolve_against(config_file, cget('DATA_DIR', 'data'))
    model_path = resolve_against(config_file, cget('MODEL_PATH', 'model.json'))
    threshold = float(cget('CONFIDENCE_THRESHOLD', '0.6'))
    min_packets = int(cget('MIN_FLOW_PACKETS', '5'))
    flow_timeout = int(cget('FLOW_TIMEOUT', '60'))
    analysis_interval = int(cget('ANALYSIS_INTERVAL', '10'))

    # On-the-fly IP ownership resolution (optional).
    ip_filter_enabled = cget('IP_FILTER_ENABLED', 'true').lower() == 'true'
    drop_confirmed_other = cget('DROP_CONFIRMED_OTHER', 'true').lower() == 'true'
    use_whois = cget('IP_FILTER_USE_WHOIS', 'false').lower() == 'true'
    ip_cache = resolve_against(config_file,
                               cget('IP_OWNERSHIP_CACHE', 'data/ip_ownership.csv'))

    # Storage layer.
    from database import InstaMonitorDB
    db = InstaMonitorDB(data_dir)

    # Classification model (optional).
    trained = model_mod.load_if_present(model_path, threshold=threshold)

    # IP ownership resolver (optional).
    resolver = None
    if ip_filter_enabled:
        resolver = ipinfo.Resolver(ip_cache, use_whois=use_whois)

    print("InstaMonitor Traffic Analyzer started")
    print(f"Config:      {config_file}")
    print(f"Packet log:  {packet_log}")
    print(f"Data dir:    {data_dir}")
    if trained:
        print(f"Model:       {model_path} "
              f"(classes: {trained.classes}, threshold {trained.threshold})")
    else:
        print(f"Model:       none found at {model_path} -- using heuristic "
              f"fallback. Train one with label.sh -> train.py.")
    if resolver is not None:
        print(f"IP filter:   on (whois={'on' if resolver.use_whois else 'off'}, "
              f"drop confirmed-other={'yes' if drop_confirmed_other else 'no'})")
    else:
        print("IP filter:   off")

    table = features.FlowTable()

    def classify(flow):
        fd = flow.features_dict()
        if trained:
            label, conf = trained.classify(flow.features())
        else:
            label, conf = heuristic_classify(fd)
        return label, conf, fd

    def record(flow):
        """Classify and persist a single finished flow (once).

        Returns the recorded label, or None if the flow was skipped/dropped.
        """
        if flow.packet_count < min_packets:
            return None

        # On-the-fly IP ownership: tag platform and optionally drop flows that
        # are confirmed to belong to an unrelated service.
        platform = None
        if resolver is not None:
            owner, method, detail = resolver.classify(flow.remote_ip)
            if owner == ipinfo.OTHER and drop_confirmed_other:
                return None  # confirmed not Instagram/TikTok -> drop
            if owner in (ipinfo.INSTAGRAM, ipinfo.TIKTOK):
                platform = owner

        label, conf, fd = classify(flow)
        try:
            db.record_flow_classification(
                device_ip=flow.local_ip,
                remote_ip=flow.remote_ip,
                platform=platform,
                activity_type=label,
                duration=fd['flow_duration'],
                packet_count=fd['pkt_count'],
                bytes_up=fd['bytes_up'],
                bytes_down=fd['bytes_down'],
                avg_packet_size=fd['pkt_size_mean'],
                packet_rate=fd['pkts_per_sec'],
                bidirectional_ratio=fd['bidirectional_ratio'],
            )
        except Exception as e:
            print(f"Warning: failed to save flow: {e}", file=sys.stderr)
        return label

    def flush_expired(now):
        counts = defaultdict(int)
        for key in table.expired(now, flow_timeout):
            flow = table.pop(key)
            if flow is None:
                continue
            label = record(flow)
            if label:
                counts[label] += 1
        return counts

    # Wait for the packet log to appear (capture.sh may start a moment later).
    waited = 0
    while not os.path.exists(packet_log) and waited < 30:
        time.sleep(1)
        waited += 1
    if not os.path.exists(packet_log):
        print(f"ERROR: packet log never appeared: {packet_log}", file=sys.stderr)
        sys.exit(1)

    last_analysis = time.time()

    try:
        with open(packet_log, 'r') as f:
            f.seek(0, 2)  # follow from end
            while True:
                line = f.readline()
                if not line:
                    now = time.time()
                    if now - last_analysis >= analysis_interval:
                        counts = flush_expired(now)
                        active = len(table.flows)
                        stamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        recorded = ', '.join(f"{k}={v}" for k, v in counts.items()) \
                            or 'none'
                        print(f"[{stamp}] active flows: {active}; "
                              f"recorded: {recorded}")
                        last_analysis = now
                    time.sleep(0.1)
                    continue

                record_tuple = features.parse_packet_line(line)
                if record_tuple:
                    table.add(record_tuple)

    except KeyboardInterrupt:
        print("\nAnalyzer stopping -- flushing remaining flows...")
        for key in list(table.flows.keys()):
            flow = table.pop(key)
            if flow is not None:
                record(flow)
        print("Analyzer stopped.")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
