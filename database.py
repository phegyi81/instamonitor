#!/usr/bin/env python3
"""
InstaMonitor CSV Storage Module
Handles storage and retrieval of traffic analysis data in CSV format
"""

import csv
import os
from datetime import datetime
from collections import defaultdict
import fcntl
from contextlib import contextmanager


class InstaMonitorDB:
    """CSV-based storage handler for InstaMonitor"""
    
    def __init__(self, data_dir):
        """Initialize CSV storage"""
        self.data_dir = data_dir
        
        # Create directory if it doesn't exist
        if not os.path.exists(data_dir):
            os.makedirs(data_dir)
        
        # CSV file paths
        self.devices_file = os.path.join(data_dir, 'devices.csv')
        self.flows_file = os.path.join(data_dir, 'flows.csv')
        self.hourly_file = os.path.join(data_dir, 'hourly_stats.csv')
        self.daily_file = os.path.join(data_dir, 'daily_stats.csv')
        
        self._init_csv_files()
        self.device_cache = {}
        self._load_devices()
    
    @contextmanager
    def _lock_file(self, filepath):
        """File locking context manager for concurrent access"""
        lockfile = filepath + '.lock'
        lock = open(lockfile, 'w')
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            lock.close()
    
    def _init_csv_files(self):
        """Initialize CSV files with headers if they don't exist"""
        
        # Devices CSV
        if not os.path.exists(self.devices_file):
            with open(self.devices_file, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['ip_address', 'mac_address', 'device_name', 
                               'first_seen', 'last_seen'])
        
        # Flows CSV (detailed flow-level data)
        if not os.path.exists(self.flows_file):
            with open(self.flows_file, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['timestamp', 'device_ip', 'remote_ip', 'platform',
                               'activity_type', 'duration_seconds', 'packet_count',
                               'bytes_up', 'bytes_down', 'avg_packet_size',
                               'packet_rate', 'bidirectional_ratio'])
        
        # Hourly stats CSV (aggregated per hour)
        if not os.path.exists(self.hourly_file):
            with open(self.hourly_file, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['timestamp', 'device_ip', 'platform', 'activity_type',
                               'total_duration_seconds', 'total_bytes', 'flow_count'])
        
        # Daily stats CSV (aggregated per day)
        if not os.path.exists(self.daily_file):
            with open(self.daily_file, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['date', 'device_ip', 'platform', 'activity_type',
                               'total_duration_seconds', 'total_bytes', 'flow_count'])
    
    def _load_devices(self):
        """Load devices into memory cache"""
        if os.path.exists(self.devices_file):
            with open(self.devices_file, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    self.device_cache[row['ip_address']] = row
    
    def get_or_create_device(self, ip_address, mac_address=None, device_name=None):
        """Get or create device entry"""
        now = datetime.now().isoformat()
        
        # Check cache first
        if ip_address in self.device_cache:
            # Update last seen
            with self._lock_file(self.devices_file):
                self._update_device_last_seen(ip_address, now)
            return ip_address
        
        # Add new device
        with self._lock_file(self.devices_file):
            with open(self.devices_file, 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([ip_address, mac_address or '', device_name or '', 
                               now, now])
            
            self.device_cache[ip_address] = {
                'ip_address': ip_address,
                'mac_address': mac_address or '',
                'device_name': device_name or '',
                'first_seen': now,
                'last_seen': now
            }
        
        return ip_address
    
    def _update_device_last_seen(self, ip_address, timestamp):
        """Update last seen timestamp for a device"""
        # Read all devices
        devices = []
        with open(self.devices_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row['ip_address'] == ip_address:
                    row['last_seen'] = timestamp
                devices.append(row)
        
        # Write back
        with open(self.devices_file, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['ip_address', 'mac_address', 
                                                   'device_name', 'first_seen', 'last_seen'])
            writer.writeheader()
            writer.writerows(devices)
        
        # Update cache
        if ip_address in self.device_cache:
            self.device_cache[ip_address]['last_seen'] = timestamp
    
    def record_flow_classification(self, device_ip, remote_ip, platform, 
                                   activity_type, duration, packet_count,
                                   bytes_up, bytes_down, avg_packet_size,
                                   packet_rate, bidirectional_ratio):
        """Record a classified flow"""
        self.get_or_create_device(device_ip)
        
        timestamp = datetime.now().isoformat()
        
        with self._lock_file(self.flows_file):
            with open(self.flows_file, 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([timestamp, device_ip, remote_ip, platform or '',
                               activity_type, f'{duration:.2f}', packet_count,
                               bytes_up, bytes_down, f'{avg_packet_size:.2f}',
                               f'{packet_rate:.2f}', f'{bidirectional_ratio:.3f}'])
        
        # Update aggregated stats
        self._update_hourly_stats(device_ip, platform or 'unknown', activity_type,
                                 duration, bytes_up + bytes_down)
        self._update_daily_stats(device_ip, platform or 'unknown', activity_type,
                                duration, bytes_up + bytes_down)
    
    def _update_hourly_stats(self, device_ip, platform, activity_type, 
                            duration, bytes_total):
        """Update hourly aggregated statistics"""
        # Round to current hour
        current_hour = datetime.now().replace(minute=0, second=0, microsecond=0).isoformat()
        
        # Read existing hourly stats
        hourly_stats = defaultdict(lambda: {'duration': 0, 'bytes': 0, 'flows': 0})
        
        with self._lock_file(self.hourly_file):
            if os.path.exists(self.hourly_file):
                with open(self.hourly_file, 'r') as f:
                    reader = csv.DictReader(f)
                    rows = []
                    for row in reader:
                        key = (row['timestamp'], row['device_ip'], row['platform'], 
                              row['activity_type'])
                        if key[0] == current_hour and key[1] == device_ip and \
                           key[2] == platform and key[3] == activity_type:
                            # Update this entry
                            hourly_stats[key]['duration'] = float(row['total_duration_seconds']) + duration
                            hourly_stats[key]['bytes'] = int(row['total_bytes']) + bytes_total
                            hourly_stats[key]['flows'] = int(row['flow_count']) + 1
                        else:
                            # Keep existing entry
                            rows.append(row)
            
            # Add current hour if not exists
            key = (current_hour, device_ip, platform, activity_type)
            if key not in hourly_stats:
                hourly_stats[key]['duration'] = duration
                hourly_stats[key]['bytes'] = bytes_total
                hourly_stats[key]['flows'] = 1
            
            # Write all entries back
            with open(self.hourly_file, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['timestamp', 'device_ip', 'platform', 'activity_type',
                               'total_duration_seconds', 'total_bytes', 'flow_count'])
                
                # Write old entries
                for row in rows:
                    writer.writerow([row['timestamp'], row['device_ip'], row['platform'],
                                   row['activity_type'], row['total_duration_seconds'],
                                   row['total_bytes'], row['flow_count']])
                
                # Write updated/new entries
                for key, stats in hourly_stats.items():
                    writer.writerow([key[0], key[1], key[2], key[3],
                                   f"{stats['duration']:.2f}", stats['bytes'], stats['flows']])
    
    def _update_daily_stats(self, device_ip, platform, activity_type,
                           duration, bytes_total):
        """Update daily aggregated statistics"""
        today = datetime.now().date().isoformat()
        
        # Read existing daily stats
        daily_stats = defaultdict(lambda: {'duration': 0, 'bytes': 0, 'flows': 0})
        
        with self._lock_file(self.daily_file):
            if os.path.exists(self.daily_file):
                with open(self.daily_file, 'r') as f:
                    reader = csv.DictReader(f)
                    rows = []
                    for row in reader:
                        key = (row['date'], row['device_ip'], row['platform'], 
                              row['activity_type'])
                        if key[0] == today and key[1] == device_ip and \
                           key[2] == platform and key[3] == activity_type:
                            # Update this entry
                            daily_stats[key]['duration'] = float(row['total_duration_seconds']) + duration
                            daily_stats[key]['bytes'] = int(row['total_bytes']) + bytes_total
                            daily_stats[key]['flows'] = int(row['flow_count']) + 1
                        else:
                            # Keep existing entry
                            rows.append(row)
            
            # Add today if not exists
            key = (today, device_ip, platform, activity_type)
            if key not in daily_stats:
                daily_stats[key]['duration'] = duration
                daily_stats[key]['bytes'] = bytes_total
                daily_stats[key]['flows'] = 1
            
            # Write all entries back
            with open(self.daily_file, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['date', 'device_ip', 'platform', 'activity_type',
                               'total_duration_seconds', 'total_bytes', 'flow_count'])
                
                # Write old entries
                for row in rows:
                    writer.writerow([row['date'], row['device_ip'], row['platform'],
                                   row['activity_type'], row['total_duration_seconds'],
                                   row['total_bytes'], row['flow_count']])
                
                # Write updated/new entries
                for key, stats in daily_stats.items():
                    writer.writerow([key[0], key[1], key[2], key[3],
                                   f"{stats['duration']:.2f}", stats['bytes'], stats['flows']])
    
    def get_device_stats(self, device_ip=None, start_date=None, end_date=None):
        """Get statistics for device(s)"""
        stats = defaultdict(lambda: {'total_seconds': 0, 'total_bytes': 0, 'sessions': 0})
        
        if not os.path.exists(self.daily_file):
            return []
        
        with open(self.daily_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Filter by device if specified
                if device_ip and row['device_ip'] != device_ip:
                    continue
                
                # Filter by date range if specified
                row_date = row['date']
                if start_date and row_date < start_date:
                    continue
                if end_date and row_date > end_date:
                    continue
                
                key = (row['device_ip'], row['platform'], row['activity_type'])
                stats[key]['total_seconds'] += float(row['total_duration_seconds'])
                stats[key]['total_bytes'] += int(row['total_bytes'])
                stats[key]['sessions'] += int(row['flow_count'])
        
        # Convert to list of dicts
        result = []
        for (device_ip, platform, activity_type), data in stats.items():
            result.append({
                'device_ip': device_ip,
                'platform': platform,
                'activity_type': activity_type,
                'total_seconds': data['total_seconds'],
                'total_bytes': data['total_bytes'],
                'sessions': data['sessions']
            })
        
        return result
    
    def get_storage_size(self):
        """Get total storage size in bytes"""
        total = 0
        for filepath in [self.devices_file, self.flows_file, 
                        self.hourly_file, self.daily_file]:
            if os.path.exists(filepath):
                total += os.path.getsize(filepath)
        return total
    
    def cleanup_old_data(self, days_to_keep=30):
        """Remove data older than specified days"""
        from datetime import timedelta
        
        cutoff_date = (datetime.now().date() - timedelta(days=days_to_keep)).isoformat()
        
        # Clean flows
        if os.path.exists(self.flows_file):
            with self._lock_file(self.flows_file):
                with open(self.flows_file, 'r') as f:
                    reader = csv.DictReader(f)
                    rows = [row for row in reader 
                           if row['timestamp'][:10] >= cutoff_date]
                
                with open(self.flows_file, 'w', newline='') as f:
                    if rows:
                        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
                        writer.writeheader()
                        writer.writerows(rows)
        
        # Clean hourly stats
        if os.path.exists(self.hourly_file):
            with self._lock_file(self.hourly_file):
                with open(self.hourly_file, 'r') as f:
                    reader = csv.DictReader(f)
                    rows = [row for row in reader 
                           if row['timestamp'][:10] >= cutoff_date]
                
                with open(self.hourly_file, 'w', newline='') as f:
                    if rows:
                        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
                        writer.writeheader()
                        writer.writerows(rows)
        
        # Clean daily stats
        if os.path.exists(self.daily_file):
            with self._lock_file(self.daily_file):
                with open(self.daily_file, 'r') as f:
                    reader = csv.DictReader(f)
                    rows = [row for row in reader 
                           if row['date'] >= cutoff_date]
                
                with open(self.daily_file, 'w', newline='') as f:
                    if rows:
                        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
                        writer.writeheader()
                        writer.writerows(rows)


if __name__ == "__main__":
    # Test the CSV storage
    import tempfile
    test_dir = tempfile.mkdtemp()
    
    db = InstaMonitorDB(test_dir)
    
    print("CSV storage initialized successfully")
    print(f"Data directory: {test_dir}")
    print(f"Storage size: {db.get_storage_size()} bytes")
    
    # Test operations
    device_ip = db.get_or_create_device("192.168.1.100", "AA:BB:CC:DD:EE:FF", "Test Device")
    print(f"Device IP: {device_ip}")
    
    # Record some test data
    db.record_flow_classification(
        "192.168.1.100", "157.240.1.1", "instagram", "video_scroll",
        45.5, 250, 5000, 125000, 500, 5.5, 0.1
    )
    
    db.record_flow_classification(
        "192.168.1.100", "157.240.1.1", "instagram", "chat",
        15.2, 80, 2000, 3000, 62.5, 8.2, 0.45
    )
    
    # Get stats
    stats = db.get_device_stats("192.168.1.100")
    print(f"\nDevice stats: {stats}")
    
    # List created files
    print(f"\nCreated files:")
    for f in os.listdir(test_dir):
        filepath = os.path.join(test_dir, f)
        print(f"  {f}: {os.path.getsize(filepath)} bytes")
    
    print("\nCSV storage test completed successfully!")
    print(f"\nYou can view the CSV files in: {test_dir}")

