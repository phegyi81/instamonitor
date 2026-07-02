#!/usr/bin/env python3
"""
InstaMonitor Database Module
Handles storage and retrieval of traffic analysis data
"""

import sqlite3
import os
from datetime import datetime
from contextlib import contextmanager


class InstaMonitorDB:
    """Database handler for InstaMonitor"""
    
    def __init__(self, db_path):
        """Initialize database connection"""
        self.db_path = db_path
        
        # Create directory if it doesn't exist
        db_dir = os.path.dirname(db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir)
        
        self._init_database()
    
    @contextmanager
    def get_connection(self):
        """Get database connection as context manager"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    def _init_database(self):
        """Initialize database schema"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Devices table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS devices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ip_address TEXT UNIQUE NOT NULL,
                    mac_address TEXT,
                    device_name TEXT,
                    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Sessions table - represents a continuous period of activity
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id INTEGER NOT NULL,
                    platform TEXT NOT NULL,  -- instagram or tiktok
                    activity_type TEXT NOT NULL,  -- chat, video_conference, video_scroll
                    start_time TIMESTAMP NOT NULL,
                    end_time TIMESTAMP,
                    duration_seconds INTEGER,
                    packets_sent INTEGER DEFAULT 0,
                    packets_received INTEGER DEFAULT 0,
                    bytes_sent INTEGER DEFAULT 0,
                    bytes_received INTEGER DEFAULT 0,
                    remote_ip TEXT,
                    FOREIGN KEY (device_id) REFERENCES devices (id)
                )
            ''')
            
            # Traffic statistics - minute-by-minute aggregation
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS traffic_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TIMESTAMP NOT NULL,
                    device_id INTEGER NOT NULL,
                    platform TEXT NOT NULL,
                    activity_type TEXT NOT NULL,
                    packets INTEGER DEFAULT 0,
                    bytes INTEGER DEFAULT 0,
                    flows INTEGER DEFAULT 0,
                    FOREIGN KEY (device_id) REFERENCES devices (id)
                )
            ''')
            
            # Flow classifications - detailed flow-level data
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS flow_classifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    device_id INTEGER NOT NULL,
                    remote_ip TEXT NOT NULL,
                    platform TEXT,
                    activity_type TEXT NOT NULL,
                    duration_seconds REAL,
                    packet_count INTEGER,
                    bytes_up INTEGER,
                    bytes_down INTEGER,
                    avg_packet_size REAL,
                    packet_rate REAL,
                    bidirectional_ratio REAL,
                    FOREIGN KEY (device_id) REFERENCES devices (id)
                )
            ''')
            
            # Daily summaries
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS daily_summaries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date DATE NOT NULL,
                    device_id INTEGER NOT NULL,
                    platform TEXT NOT NULL,
                    activity_type TEXT NOT NULL,
                    total_duration_seconds INTEGER DEFAULT 0,
                    total_bytes INTEGER DEFAULT 0,
                    session_count INTEGER DEFAULT 0,
                    UNIQUE(date, device_id, platform, activity_type),
                    FOREIGN KEY (device_id) REFERENCES devices (id)
                )
            ''')
            
            # Create indices for better query performance
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_sessions_device_time 
                ON sessions(device_id, start_time)
            ''')
            
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_traffic_stats_timestamp 
                ON traffic_stats(timestamp, device_id)
            ''')
            
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_flow_timestamp 
                ON flow_classifications(timestamp, device_id)
            ''')
            
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_daily_summaries_date 
                ON daily_summaries(date, device_id)
            ''')
            
            conn.commit()
    
    def get_or_create_device(self, ip_address, mac_address=None, device_name=None):
        """Get device ID or create new device entry"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Try to find existing device
            cursor.execute('SELECT id FROM devices WHERE ip_address = ?', (ip_address,))
            row = cursor.fetchone()
            
            if row:
                device_id = row[0]
                # Update last seen
                cursor.execute(
                    'UPDATE devices SET last_seen = CURRENT_TIMESTAMP WHERE id = ?',
                    (device_id,)
                )
            else:
                # Create new device
                cursor.execute(
                    '''INSERT INTO devices (ip_address, mac_address, device_name) 
                       VALUES (?, ?, ?)''',
                    (ip_address, mac_address, device_name)
                )
                device_id = cursor.lastrowid
            
            conn.commit()
            return device_id
    
    def record_flow_classification(self, device_ip, remote_ip, platform, 
                                   activity_type, duration, packet_count,
                                   bytes_up, bytes_down, avg_packet_size,
                                   packet_rate, bidirectional_ratio):
        """Record a classified flow"""
        device_id = self.get_or_create_device(device_ip)
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO flow_classifications 
                (device_id, remote_ip, platform, activity_type, duration_seconds,
                 packet_count, bytes_up, bytes_down, avg_packet_size,
                 packet_rate, bidirectional_ratio)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (device_id, remote_ip, platform, activity_type, duration,
                  packet_count, bytes_up, bytes_down, avg_packet_size,
                  packet_rate, bidirectional_ratio))
            
            conn.commit()
            return cursor.lastrowid
    
    def update_traffic_stats(self, device_ip, platform, activity_type, 
                            packets, bytes_transferred, flows=1):
        """Update minute-by-minute traffic statistics"""
        device_id = self.get_or_create_device(device_ip)
        
        # Round timestamp to nearest minute
        timestamp = datetime.now().replace(second=0, microsecond=0)
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Check if entry exists for this minute
            cursor.execute('''
                SELECT id, packets, bytes, flows FROM traffic_stats
                WHERE timestamp = ? AND device_id = ? 
                  AND platform = ? AND activity_type = ?
            ''', (timestamp, device_id, platform, activity_type))
            
            row = cursor.fetchone()
            
            if row:
                # Update existing entry
                cursor.execute('''
                    UPDATE traffic_stats 
                    SET packets = packets + ?,
                        bytes = bytes + ?,
                        flows = flows + ?
                    WHERE id = ?
                ''', (packets, bytes_transferred, flows, row[0]))
            else:
                # Insert new entry
                cursor.execute('''
                    INSERT INTO traffic_stats 
                    (timestamp, device_id, platform, activity_type, 
                     packets, bytes, flows)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (timestamp, device_id, platform, activity_type,
                      packets, bytes_transferred, flows))
            
            conn.commit()
    
    def start_session(self, device_ip, platform, activity_type, remote_ip):
        """Start a new activity session"""
        device_id = self.get_or_create_device(device_ip)
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO sessions 
                (device_id, platform, activity_type, start_time, remote_ip)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP, ?)
            ''', (device_id, platform, activity_type, remote_ip))
            
            conn.commit()
            return cursor.lastrowid
    
    def end_session(self, session_id, packets_sent, packets_received,
                   bytes_sent, bytes_received):
        """End an activity session and update statistics"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE sessions
                SET end_time = CURRENT_TIMESTAMP,
                    duration_seconds = CAST((julianday(CURRENT_TIMESTAMP) - julianday(start_time)) * 86400 AS INTEGER),
                    packets_sent = ?,
                    packets_received = ?,
                    bytes_sent = ?,
                    bytes_received = ?
                WHERE id = ?
            ''', (packets_sent, packets_received, bytes_sent, 
                  bytes_received, session_id))
            
            conn.commit()
    
    def update_daily_summary(self, device_ip, platform, activity_type, 
                            duration_seconds, bytes_transferred):
        """Update daily summary statistics"""
        device_id = self.get_or_create_device(device_ip)
        today = datetime.now().date()
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO daily_summaries 
                (date, device_id, platform, activity_type, 
                 total_duration_seconds, total_bytes, session_count)
                VALUES (?, ?, ?, ?, ?, ?, 1)
                ON CONFLICT(date, device_id, platform, activity_type) 
                DO UPDATE SET
                    total_duration_seconds = total_duration_seconds + ?,
                    total_bytes = total_bytes + ?,
                    session_count = session_count + 1
            ''', (today, device_id, platform, activity_type, 
                  duration_seconds, bytes_transferred,
                  duration_seconds, bytes_transferred))
            
            conn.commit()
    
    def get_device_stats(self, device_ip, start_date=None, end_date=None):
        """Get statistics for a specific device"""
        device_id = self.get_or_create_device(device_ip)
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            query = '''
                SELECT platform, activity_type,
                       SUM(total_duration_seconds) as total_seconds,
                       SUM(total_bytes) as total_bytes,
                       SUM(session_count) as sessions
                FROM daily_summaries
                WHERE device_id = ?
            '''
            params = [device_id]
            
            if start_date:
                query += ' AND date >= ?'
                params.append(start_date)
            
            if end_date:
                query += ' AND date <= ?'
                params.append(end_date)
            
            query += ' GROUP BY platform, activity_type'
            
            cursor.execute(query, params)
            
            return [dict(row) for row in cursor.fetchall()]
    
    def get_database_size(self):
        """Get database file size in bytes"""
        if os.path.exists(self.db_path):
            return os.path.getsize(self.db_path)
        return 0
    
    def cleanup_old_data(self, days_to_keep=30):
        """Remove data older than specified days"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cutoff_date = datetime.now().date()
            cutoff_date = cutoff_date.replace(day=cutoff_date.day - days_to_keep)
            
            cursor.execute('DELETE FROM flow_classifications WHERE date(timestamp) < ?', 
                         (cutoff_date,))
            cursor.execute('DELETE FROM traffic_stats WHERE date(timestamp) < ?', 
                         (cutoff_date,))
            cursor.execute('DELETE FROM sessions WHERE date(start_time) < ?', 
                         (cutoff_date,))
            cursor.execute('DELETE FROM daily_summaries WHERE date < ?', 
                         (cutoff_date,))
            
            conn.commit()
            
            # Vacuum to reclaim space
            cursor.execute('VACUUM')


if __name__ == "__main__":
    # Test the database
    db = InstaMonitorDB("/tmp/test_instamonitor.db")
    
    print("Database initialized successfully")
    print(f"Database size: {db.get_database_size()} bytes")
    
    # Test operations
    device_id = db.get_or_create_device("192.168.1.100", "AA:BB:CC:DD:EE:FF", "Test Device")
    print(f"Device ID: {device_id}")
    
    # Record some test data
    db.record_flow_classification(
        "192.168.1.100", "157.240.1.1", "instagram", "video_scroll",
        45.5, 250, 5000, 125000, 500, 5.5, 0.1
    )
    
    db.update_traffic_stats("192.168.1.100", "instagram", "video_scroll", 
                           250, 130000, 1)
    
    db.update_daily_summary("192.168.1.100", "instagram", "video_scroll", 
                           45, 130000)
    
    # Get stats
    stats = db.get_device_stats("192.168.1.100")
    print(f"\nDevice stats: {stats}")
    
    print("\nDatabase test completed successfully!")
