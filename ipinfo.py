#!/usr/bin/env python3
"""
InstaMonitor IP Ownership Resolver
==================================

On-the-fly identification of remote IP addresses so the analyzer can:

  * tag each flow with the platform it belongs to (instagram / tiktok), and
  * drop flows that are *confirmed* to belong to an unrelated service.

Design principles for the weak OpenWrt router:

  * Every distinct IP is resolved AT MOST ONCE, then cached forever in a CSV
    (data/ip_ownership.csv). Repeated flows to the same IP cost nothing.
  * Reverse DNS (a single, cheap, stdlib lookup) is the primary signal.
  * WHOIS is optional (off by default) and only consulted when reverse DNS is
    inconclusive; it is better at spotting ByteDance/TikTok CDN ranges.

Classification result is one of:
  instagram | tiktok | other | unknown

Policy (implemented by the caller, e.g. analyzer.py):
  * instagram / tiktok  -> keep, tag platform
  * unknown             -> keep (we could not prove it is unrelated)
  * other               -> may be dropped (confirmed NOT Instagram/TikTok)

The pattern tables below are the single place to tune identification. They
match against reverse-DNS hostnames and WHOIS org/netname text (lowercased).
"""

import csv
import os
import socket
import subprocess
import shutil
from datetime import datetime

INSTAGRAM = 'instagram'
TIKTOK = 'tiktok'
OTHER = 'other'
UNKNOWN = 'unknown'

# Substrings that positively identify Instagram / Meta infrastructure.
INSTAGRAM_PATTERNS = (
    'instagram', 'fbcdn', 'facebook', 'fbsv', 'fna.fbcdn', 'cstates.fbcdn',
    'meta platforms', 'facebook, inc', 'facebook ireland',
)

# Substrings that positively identify TikTok / ByteDance infrastructure.
TIKTOK_PATTERNS = (
    'tiktok', 'tiktokcdn', 'tiktokv', 'byteoversea', 'ibyteimg', 'pstatp',
    'bytedance', 'bytecdn', 'bytefcdn', 'muscdn', 'ipstatp', 'sgsnssdk',
)

# Substrings that positively identify clearly-UNRELATED services. Only put
# owners here that Instagram/TikTok are NOT known to serve media through, so
# dropping them is safe. Ambiguous CDNs (akamai, fastly, cloudflare, amazon)
# are intentionally absent -> they resolve to "unknown" and are kept.
OTHER_PATTERNS = (
    'googlevideo', 'youtube', 'ytimg', 'gstatic', 'gvt1', '1e100',
    'googleusercontent', 'google.com',
    'netflix', 'nflxvideo', 'nflxso', 'nflximg',
    'spotify', 'scdn.co', 'pscdn',
    'apple', 'icloud', 'aaplimg', 'mzstatic',
    'windowsupdate', 'microsoft', 'msftncsi', 'msedge', 'xboxlive',
    'whatsapp', 'wa.me',
    'snapchat', 'sc-cdn', 'snap-dev',
    'twitter', 'twimg', 'x.com',
    'discord', 'discordapp',
)

CACHE_HEADER = ['ip', 'platform', 'method', 'detail', 'resolved_at']


def _ip_to_int(ip):
    """Convert a dotted-quad IPv4 string to an int, or None if invalid."""
    parts = ip.split('.')
    if len(parts) != 4:
        return None
    try:
        octets = [int(p) for p in parts]
    except ValueError:
        return None
    if any(o < 0 or o > 255 for o in octets):
        return None
    return (octets[0] << 24) | (octets[1] << 16) | (octets[2] << 8) | octets[3]


def _parse_cidr(cidr):
    """Parse 'a.b.c.d/prefix' into (network_int, mask_int), or None.

    IPv4 only and stdlib-free (no 'ipaddress' import) so it is safe on the
    python3-light build shipped with OpenWrt.
    """
    if '/' not in cidr:
        return None
    net, _, bits = cidr.partition('/')
    net_int = _ip_to_int(net)
    if net_int is None:
        return None
    try:
        prefix = int(bits)
    except ValueError:
        return None
    if prefix < 0 or prefix > 32:
        return None
    mask = (0xFFFFFFFF << (32 - prefix)) & 0xFFFFFFFF if prefix else 0
    return (net_int & mask, mask)


def _match(text):
    """Return a platform label if text matches a known pattern, else None."""
    t = text.lower()
    for p in INSTAGRAM_PATTERNS:
        if p in t:
            return INSTAGRAM
    for p in TIKTOK_PATTERNS:
        if p in t:
            return TIKTOK
    for p in OTHER_PATTERNS:
        if p in t:
            return OTHER
    return None


class Resolver:
    """Resolves and caches IP ownership."""

    def __init__(self, cache_path, use_whois=False, dns_timeout=2.0,
                 whois_timeout=5):
        self.cache_path = cache_path
        self.use_whois = use_whois and shutil.which('whois') is not None
        self.dns_timeout = dns_timeout
        self.whois_timeout = whois_timeout
        self.cache = {}
        # Seeded CIDR ranges: list of (network_int, mask_int, platform,
        # method, detail). Populated from '/'-bearing rows in the cache file.
        self.networks = []
        self._load_cache()

    def _load_cache(self):
        if not os.path.exists(self.cache_path):
            return
        try:
            with open(self.cache_path, newline='') as f:
                for row in csv.DictReader(f):
                    ip = row['ip']
                    entry = (row['platform'], row['method'], row['detail'])
                    if '/' in ip:
                        net = _parse_cidr(ip)
                        if net is not None:
                            self.networks.append((net[0], net[1]) + entry)
                    else:
                        self.cache[ip] = entry
        except (OSError, KeyError):
            pass

    def _match_networks(self, ip):
        """Return (platform, method, detail) if ip falls in a seeded CIDR."""
        if not self.networks:
            return None
        ip_int = _ip_to_int(ip)
        if ip_int is None:
            return None
        for net_int, mask, platform, method, detail in self.networks:
            if (ip_int & mask) == net_int:
                return (platform, method, detail)
        return None

    def _append_cache(self, ip, platform, method, detail):
        out_dir = os.path.dirname(os.path.abspath(self.cache_path))
        if out_dir and not os.path.exists(out_dir):
            os.makedirs(out_dir)
        new_file = not (os.path.exists(self.cache_path)
                        and os.path.getsize(self.cache_path) > 0)
        with open(self.cache_path, 'a', newline='') as f:
            writer = csv.writer(f)
            if new_file:
                writer.writerow(CACHE_HEADER)
            writer.writerow([ip, platform, method, detail,
                             datetime.now().isoformat()])

    def _reverse_dns(self, ip):
        old = socket.getdefaulttimeout()
        socket.setdefaulttimeout(self.dns_timeout)
        try:
            hostname, aliases, _ = socket.gethostbyaddr(ip)
            names = ' '.join([hostname] + list(aliases))
            return names
        except (socket.herror, socket.gaierror, OSError):
            return ''
        finally:
            socket.setdefaulttimeout(old)

    def _whois(self, ip):
        try:
            proc = subprocess.run(
                ['whois', ip], capture_output=True, text=True,
                timeout=self.whois_timeout)
            return proc.stdout or ''
        except (subprocess.SubprocessError, OSError):
            return ''

    def classify(self, ip):
        """Return (platform, method, detail). Cached after first resolution."""
        cached = self.cache.get(ip)
        if cached is not None:
            return cached

        # 0) Seeded CIDR ranges (free, authoritative) -- checked before any
        #    network lookup so pre-seeded ranges save reverse-DNS/whois queries.
        net_hit = self._match_networks(ip)
        if net_hit is not None:
            self.cache[ip] = net_hit  # remember exact IP for the rest of the run
            return net_hit

        # 1) Reverse DNS (cheap).
        names = self._reverse_dns(ip)
        if names:
            hit = _match(names)
            if hit is not None:
                result = (hit, 'rdns', names.strip()[:120])
                self.cache[ip] = result
                self._append_cache(ip, *result)
                return result

        # 2) WHOIS (optional, only if reverse DNS was inconclusive).
        if self.use_whois:
            whois_text = self._whois(ip)
            if whois_text:
                hit = _match(whois_text)
                if hit is not None:
                    # Extract a short org/netname line for the cache detail.
                    detail = ''
                    for line in whois_text.splitlines():
                        low = line.lower()
                        if any(k in low for k in
                               ('orgname', 'org-name', 'netname', 'descr',
                                'organization', 'owner')):
                            detail = line.strip()[:120]
                            break
                    result = (hit, 'whois', detail or 'whois-match')
                    self.cache[ip] = result
                    self._append_cache(ip, *result)
                    return result

        # 3) Could not prove anything -> unknown (kept by policy).
        result = (UNKNOWN, 'none', names.strip()[:120] if names else '')
        self.cache[ip] = result
        self._append_cache(ip, *result)
        return result


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description='Resolve IP ownership (instagram/tiktok/other/unknown).')
    parser.add_argument('ips', nargs='+', help='IP address(es) to classify.')
    parser.add_argument('--cache', default='data/ip_ownership.csv',
                        help='Cache CSV path (default data/ip_ownership.csv).')
    parser.add_argument('--whois', action='store_true',
                        help='Also consult whois when reverse DNS is unclear.')
    args = parser.parse_args()

    resolver = Resolver(args.cache, use_whois=args.whois)
    for ip in args.ips:
        platform, method, detail = resolver.classify(ip)
        print(f"{ip}\t{platform}\t{method}\t{detail}")


if __name__ == '__main__':
    main()
