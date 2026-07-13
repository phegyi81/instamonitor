#!/usr/bin/env python3
"""
InstaMonitor Flow Feature Extractor
====================================

Single source of truth for turning raw packet records into per-flow feature
vectors. Both the offline training pipeline (label.sh -> train.py) and the
live analyzer (analyzer.py) import this module so the features are guaranteed
to be computed identically in both places.

Packet record format (produced by parse_packets.awk), pipe separated:

    epoch_ts|proto|src_ip|src_port|dst_ip|dst_port|length

A "flow" is one bidirectional connection identified by the 5-tuple
(proto, local_ip, local_port, remote_ip, remote_port), normalized so the
local (LAN) endpoint is always the "source" side.

CLI usage (offline feature extraction, used by label.sh):

    features.py --input <packet_log> [--label LABEL] \
                [--output data/training_data.csv] [--append] \
                [--min-packets 5]

With no --label the label column is omitted (useful for ad-hoc inspection).
"""

import argparse
import csv
import os
import sys
import statistics


# Canonical feature order. MUST stay stable: train.py records this order in
# the model and model.py relies on it. Append new features at the end only.
FEATURE_NAMES = [
    'pkt_count',
    'bytes_up',
    'bytes_down',
    'total_bytes',
    'flow_duration',
    'bytes_per_sec_up',
    'bytes_per_sec_down',
    'pkts_per_sec',
    'pkt_size_mean',
    'pkt_size_std',
    'pkt_size_min',
    'pkt_size_max',
    'pkt_size_median',
    'pkt_size_up_mean',
    'pkt_size_up_std',
    'pkt_size_down_mean',
    'pkt_size_down_std',
    'iat_mean',
    'iat_std',
    'iat_min',
    'iat_max',
    'iat_median',
    'download_ratio',
    'bidirectional_ratio',
    'burst_ratio',
]

# Default private-network prefixes used to decide which endpoint is local.
LOCAL_PREFIXES = ('192.168.', '10.', '172.16.', '172.17.', '172.18.',
                  '172.19.', '172.20.', '172.21.', '172.22.', '172.23.',
                  '172.24.', '172.25.', '172.26.', '172.27.', '172.28.',
                  '172.29.', '172.30.', '172.31.')


def is_local_ip(ip):
    """Return True if ip is in a private LAN range."""
    return ip.startswith(LOCAL_PREFIXES)


def _mean(values):
    return statistics.mean(values) if values else 0.0


def _std(values):
    # Population standard deviation; defined for a single value (0.0).
    return statistics.pstdev(values) if len(values) >= 1 else 0.0


def _median(values):
    return statistics.median(values) if values else 0.0


class Flow:
    """Accumulates packets for one connection and computes feature vectors."""

    def __init__(self, proto, local_ip, local_port, remote_ip, remote_port):
        self.proto = proto
        self.local_ip = local_ip
        self.local_port = local_port
        self.remote_ip = remote_ip
        self.remote_port = remote_port

        self.start_time = None
        self.last_time = None

        # Per-packet arrays keep everything the features need.
        self.up_sizes = []      # local -> remote (upload)
        self.down_sizes = []    # remote -> local (download)
        self.timestamps = []    # arrival times of all packets, in order

    def add_packet(self, ts, src_ip, length):
        """Add one packet. src_ip decides direction."""
        if self.start_time is None:
            self.start_time = ts
        self.last_time = ts
        self.timestamps.append(ts)

        if src_ip == self.local_ip:
            self.up_sizes.append(length)
        else:
            self.down_sizes.append(length)

    @property
    def packet_count(self):
        return len(self.up_sizes) + len(self.down_sizes)

    def duration(self):
        if self.start_time is None or self.last_time is None:
            return 0.0
        return self.last_time - self.start_time

    def _inter_arrival_times(self):
        if len(self.timestamps) < 2:
            return []
        ordered = sorted(self.timestamps)
        return [ordered[i] - ordered[i - 1] for i in range(1, len(ordered))]

    def features(self):
        """Return an ordered list of feature values (matches FEATURE_NAMES)."""
        all_sizes = self.up_sizes + self.down_sizes
        n = len(all_sizes)
        n_up = len(self.up_sizes)
        n_down = len(self.down_sizes)
        dur = self.duration()

        bytes_up = sum(self.up_sizes)
        bytes_down = sum(self.down_sizes)
        total_bytes = bytes_up + bytes_down

        # Rates (guard against zero-duration flows).
        if dur > 0:
            bps_up = bytes_up / dur
            bps_down = bytes_down / dur
            pps = n / dur
        else:
            bps_up = bps_down = pps = 0.0

        # Inter-packet times and a continuous burstiness measure: the fraction
        # of gaps that are much shorter than the mean gap (i.e. packet bursts).
        iats = self._inter_arrival_times()
        if iats:
            iat_mean = _mean(iats)
            iat_std = _std(iats)
            iat_min = min(iats)
            iat_max = max(iats)
            iat_med = _median(iats)
            if iat_mean > 0:
                burst_ratio = sum(1 for i in iats if i < iat_mean / 5.0) / len(iats)
            else:
                burst_ratio = 0.0
        else:
            iat_mean = iat_std = iat_min = iat_max = iat_med = 0.0
            burst_ratio = 0.0

        download_ratio = (n_down / n) if n else 0.0
        bidirectional_ratio = (min(n_up, n_down) / n) if n else 0.0

        values = {
            'pkt_count': n,
            'bytes_up': bytes_up,
            'bytes_down': bytes_down,
            'total_bytes': total_bytes,
            'flow_duration': round(dur, 4),
            'bytes_per_sec_up': round(bps_up, 4),
            'bytes_per_sec_down': round(bps_down, 4),
            'pkts_per_sec': round(pps, 4),
            'pkt_size_mean': round(_mean(all_sizes), 4),
            'pkt_size_std': round(_std(all_sizes), 4),
            'pkt_size_min': min(all_sizes) if all_sizes else 0,
            'pkt_size_max': max(all_sizes) if all_sizes else 0,
            'pkt_size_median': round(_median(all_sizes), 4),
            'pkt_size_up_mean': round(_mean(self.up_sizes), 4),
            'pkt_size_up_std': round(_std(self.up_sizes), 4),
            'pkt_size_down_mean': round(_mean(self.down_sizes), 4),
            'pkt_size_down_std': round(_std(self.down_sizes), 4),
            'iat_mean': round(iat_mean, 6),
            'iat_std': round(iat_std, 6),
            'iat_min': round(iat_min, 6),
            'iat_max': round(iat_max, 6),
            'iat_median': round(iat_med, 6),
            'download_ratio': round(download_ratio, 4),
            'bidirectional_ratio': round(bidirectional_ratio, 4),
            'burst_ratio': round(burst_ratio, 4),
        }
        return [values[name] for name in FEATURE_NAMES]

    def features_dict(self):
        """Return features as a name->value dict."""
        return dict(zip(FEATURE_NAMES, self.features()))


def parse_packet_line(line):
    """Parse one packet record. Returns tuple or None.

    (ts, proto, src_ip, src_port, dst_ip, dst_port, length)
    """
    parts = line.strip().split('|')
    if len(parts) != 7:
        return None
    try:
        ts = float(parts[0])
        proto = parts[1]
        src_ip = parts[2]
        src_port = int(parts[3])
        dst_ip = parts[4]
        dst_port = int(parts[5])
        length = int(parts[6])
    except (ValueError, IndexError):
        return None
    return ts, proto, src_ip, src_port, dst_ip, dst_port, length


def flow_key(proto, src_ip, src_port, dst_ip, dst_port):
    """Build a direction-independent flow key, local endpoint first.

    Returns (key_tuple, local_ip, local_port, remote_ip, remote_port).
    """
    if is_local_ip(src_ip):
        local_ip, local_port, remote_ip, remote_port = src_ip, src_port, dst_ip, dst_port
    elif is_local_ip(dst_ip):
        local_ip, local_port, remote_ip, remote_port = dst_ip, dst_port, src_ip, src_port
    else:
        # Neither endpoint is local; fall back to src as local so we still
        # group consistently.
        local_ip, local_port, remote_ip, remote_port = src_ip, src_port, dst_ip, dst_port
    key = (proto, local_ip, local_port, remote_ip, remote_port)
    return key, local_ip, local_port, remote_ip, remote_port


class FlowTable:
    """Maintains active flows keyed by 5-tuple."""

    def __init__(self):
        self.flows = {}

    def add(self, record):
        ts, proto, src_ip, src_port, dst_ip, dst_port, length = record
        key, lip, lport, rip, rport = flow_key(proto, src_ip, src_port,
                                                dst_ip, dst_port)
        flow = self.flows.get(key)
        if flow is None:
            flow = Flow(proto, lip, lport, rip, rport)
            self.flows[key] = flow
        flow.add_packet(ts, src_ip, length)
        return key

    def expired(self, now, timeout):
        """Return keys of flows idle for longer than timeout seconds."""
        return [k for k, f in self.flows.items()
                if f.last_time is not None and now - f.last_time > timeout]

    def pop(self, key):
        return self.flows.pop(key, None)


def extract_flows(input_path, min_packets=5):
    """Read a packet log fully and yield Flow objects with >= min_packets."""
    table = FlowTable()
    with open(input_path, 'r') as f:
        for line in f:
            record = parse_packet_line(line)
            if record:
                table.add(record)
    for flow in table.flows.values():
        if flow.packet_count >= min_packets:
            yield flow


def _write_rows(flows, output_path, label, append):
    header = list(FEATURE_NAMES)
    if label is not None:
        header = header + ['label']

    file_exists = os.path.exists(output_path) and os.path.getsize(output_path) > 0
    mode = 'a' if append else 'w'

    out_dir = os.path.dirname(os.path.abspath(output_path))
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir)

    written = 0
    with open(output_path, mode, newline='') as f:
        writer = csv.writer(f)
        if not (append and file_exists):
            writer.writerow(header)
        for flow in flows:
            row = flow.features()
            if label is not None:
                row = row + [label]
            writer.writerow(row)
            written += 1
    return written


def main():
    parser = argparse.ArgumentParser(
        description='Extract per-flow feature vectors from a packet log.')
    parser.add_argument('--input', required=True,
                        help='Packet log file (parse_packets.awk format).')
    parser.add_argument('--output', default='-',
                        help="Output CSV path, or '-' for stdout (default).")
    parser.add_argument('--label', default=None,
                        help='If set, append this label to every row.')
    parser.add_argument('--append', action='store_true',
                        help='Append to the output CSV instead of overwriting.')
    parser.add_argument('--min-packets', type=int, default=5,
                        help='Skip flows with fewer packets (default 5).')
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"ERROR: input not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    flows = list(extract_flows(args.input, args.min_packets))

    if args.output == '-':
        header = list(FEATURE_NAMES)
        if args.label is not None:
            header = header + ['label']
        writer = csv.writer(sys.stdout)
        writer.writerow(header)
        for flow in flows:
            row = flow.features()
            if args.label is not None:
                row = row + [args.label]
            writer.writerow(row)
        print(f"# {len(flows)} flows", file=sys.stderr)
    else:
        n = _write_rows(flows, args.output, args.label, args.append)
        action = 'appended to' if args.append else 'wrote'
        print(f"{action} {args.output}: {n} flow(s)"
              + (f" labeled '{args.label}'" if args.label else ""))


if __name__ == '__main__':
    main()
