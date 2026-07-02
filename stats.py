#!/usr/bin/env python3
"""InstaMonitor Statistics Utility - CSV Edition

Reads the CSV data produced by the analyzer and prints a human-readable
usage summary. All data is read from the project's data directory.

Usage:
    stats.py [--device IP] [--today|--yesterday|--week] [--export FILE]
             [--data-dir DIR]

If --data-dir is not given, the "data" folder next to this script is used.
"""

import sys
import os
import csv
from datetime import datetime, timedelta
import argparse
from collections import defaultdict

# Directory this script lives in; used to locate the default data folder.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DATA_DIR = os.path.join(SCRIPT_DIR, 'data')


def format_bytes(bytes_val):
    """Format bytes in human-readable format"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_val < 1024.0:
            return f"{bytes_val:.2f} {unit}"
        bytes_val /= 1024.0
    return f"{bytes_val:.2f} TB"


def format_duration(seconds):
    """Format seconds as hours:minutes:seconds"""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def read_daily_stats(data_dir, device_ip=None, start_date=None, end_date=None):
    """Read daily statistics from CSV"""
    daily_file = os.path.join(data_dir, 'daily_stats.csv')
    if not os.path.exists(daily_file):
        return []

    stats = defaultdict(lambda: {'total_seconds': 0, 'total_bytes': 0, 'sessions': 0})

    with open(daily_file, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if device_ip and row['device_ip'] != device_ip:
                continue
            if start_date and row['date'] < start_date:
                continue
            if end_date and row['date'] > end_date:
                continue

            key = (row['device_ip'], row['platform'], row['activity_type'])
            stats[key]['total_seconds'] += float(row['total_duration_seconds'])
            stats[key]['total_bytes'] += int(row['total_bytes'])
            stats[key]['sessions'] += int(row['flow_count'])

    result = []
    for (dev_ip, platform, activity), data in stats.items():
        result.append({
            'device_ip': dev_ip,
            'platform': platform,
            'activity_type': activity,
            'total_seconds': data['total_seconds'],
            'total_bytes': data['total_bytes'],
            'sessions': data['sessions']
        })
    return result


def main():
    parser = argparse.ArgumentParser(description='InstaMonitor Statistics')
    parser.add_argument('--device', help='Device IP address')
    parser.add_argument('--today', action='store_true', help='Show today\'s stats')
    parser.add_argument('--yesterday', action='store_true', help='Show yesterday\'s stats')
    parser.add_argument('--week', action='store_true', help='Show this week\'s stats')
    parser.add_argument('--export', help='Export to CSV file')
    parser.add_argument('--data-dir', default=DEFAULT_DATA_DIR,
                        help='Data directory (default: ./data next to this script)')

    args = parser.parse_args()

    data_dir = args.data_dir

    # Determine date range
    if args.today:
        start_date = str(datetime.now().date())
        end_date = start_date
    elif args.yesterday:
        start_date = str((datetime.now() - timedelta(days=1)).date())
        end_date = start_date
    elif args.week:
        end_date = str(datetime.now().date())
        start_date = str((datetime.now() - timedelta(days=7)).date())
    else:
        start_date = None
        end_date = None

    # Get stats
    if args.device:
        stats = read_daily_stats(data_dir, args.device, start_date, end_date)
        print(f"\nStatistics for {args.device}")
    else:
        print("\nOverall Statistics")
        stats = read_daily_stats(data_dir, None, start_date, end_date)

    if start_date:
        print(f"Period: {start_date} to {end_date}")
    else:
        print("Period: All time")

    print("\n" + "=" * 80)
    print(f"{'Platform':<12} {'Activity':<20} {'Duration':<15} {'Data':<15} {'Sessions':<10}")
    print("=" * 80)

    total_seconds = 0
    total_bytes = 0

    for stat in stats:
        duration = format_duration(int(stat['total_seconds']))
        data = format_bytes(int(stat['total_bytes']))

        print(f"{stat['platform']:<12} {stat['activity_type']:<20} "
              f"{duration:<15} {data:<15} {stat['sessions']:<10}")

        total_seconds += stat['total_seconds']
        total_bytes += stat['total_bytes']

    print("=" * 80)
    print(f"{'TOTAL':<12} {'':<20} {format_duration(int(total_seconds)):<15} "
          f"{format_bytes(int(total_bytes)):<15}")
    print("=" * 80)

    if args.export:
        # Export to CSV
        with open(args.export, 'w') as f:
            f.write("Device IP,Platform,Activity,Duration (seconds),Bytes,Sessions\n")
            for stat in stats:
                f.write(f"{stat.get('device_ip', 'All')},{stat['platform']},{stat['activity_type']},"
                        f"{stat['total_seconds']},{stat['total_bytes']},"
                        f"{stat['sessions']}\n")
        print(f"\nExported to {args.export}")


if __name__ == '__main__':
    main()
