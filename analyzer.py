#!/usr/bin/env python3
"""
InstaMonitor Traffic Analyzer
Analyzes packet metadata to classify social media usage patterns
Stores results in CSV files for easy analysis
"""

import sys
import os
import time
import configparser
import re
from collections import defaultdict, deque
from datetime import datetime
from enum import Enum
import statistics


class ActivityType(Enum):
    """Types of social media activities"""
    CHAT = "chat"
    VIDEO_CONFERENCE = "video_conference"
    VIDEO_SCROLL = "video_scroll"
    UNKNOWN = "unknown"


class PacketFlow:
    """Represents a flow of packets between two endpoints"""
    
    def __init__(self, src_ip, dst_ip):
        self.src_ip = src_ip
        self.dst_ip = dst_ip
        self.packets = []
        self.start_time = None
        self.last_time = None
        self.total_bytes_up = 0
        self.total_bytes_down = 0
        self.packet_count_up = 0
        self.packet_count_down = 0
        
    def add_packet(self, timestamp, src_ip, dst_ip, length):
        """Add a packet to the flow"""
        if self.start_time is None:
            self.start_time = timestamp
        
        self.last_time = timestamp
        
        # Determine direction (upload vs download)
        is_upload = (src_ip == self.src_ip)
        
        if is_upload:
            self.total_bytes_up += length
            self.packet_count_up += 1
        else:
            self.total_bytes_down += length
            self.packet_count_down += 1
        
        self.packets.append({
            'timestamp': timestamp,
            'length': length,
            'direction': 'up' if is_upload else 'down'
        })
    
    def get_duration(self):
        """Get flow duration in seconds"""
        if self.start_time is None or self.last_time is None:
            return 0
        return self.last_time - self.start_time
    
    def get_packet_rate(self):
        """Get average packets per second"""
        duration = self.get_duration()
        if duration == 0:
            return 0
        return len(self.packets) / duration
    
    def get_bidirectional_ratio(self):
        """Get ratio of traffic in both directions (0-1)"""
        total_packets = self.packet_count_up + self.packet_count_down
        if total_packets == 0:
            return 0
        
        min_direction = min(self.packet_count_up, self.packet_count_down)
        return min_direction / total_packets
    
    def get_download_ratio(self):
        """Get ratio of download traffic"""
        total_packets = self.packet_count_up + self.packet_count_down
        if total_packets == 0:
            return 0
        return self.packet_count_down / total_packets
    
    def get_average_packet_size(self):
        """Get average packet size"""
        if not self.packets:
            return 0
        return statistics.mean([p['length'] for p in self.packets])
    
    def get_packet_size_variance(self):
        """Get variance in packet sizes"""
        if len(self.packets) < 2:
            return 0
        sizes = [p['length'] for p in self.packets]
        return statistics.variance(sizes)
    
    def is_bursty(self, threshold=5):
        """Check if traffic is bursty"""
        if len(self.packets) < 10:
            return False
        
        # Calculate packet arrival intervals
        intervals = []
        for i in range(1, len(self.packets)):
            interval = self.packets[i]['timestamp'] - self.packets[i-1]['timestamp']
            if interval > 0:
                intervals.append(interval)
        
        if not intervals:
            return False
        
        avg_interval = statistics.mean(intervals)
        
        # Check for bursts (very short intervals compared to average)
        burst_count = sum(1 for i in intervals if i < avg_interval / threshold)
        
        return burst_count > len(intervals) * 0.3


class TrafficAnalyzer:
    """Analyzes traffic patterns to classify activities"""
    
    def __init__(self, config_file):
        """Initialize analyzer with configuration"""
        self.config = self.load_config(config_file)
        self.flows = {}
        self.flow_timeout = 60  # seconds
        self.local_networks = ['192.168.', '10.', '172.16.']
        
    def load_config(self, config_file):
        """Load configuration from file"""
        config = configparser.ConfigParser()
        config.read(config_file)
        
        return {
            'chat_max_size': int(config.get('DEFAULT', 'CHAT_PACKET_SIZE_MAX', fallback='500')),
            'chat_min_pps': float(config.get('DEFAULT', 'CHAT_MIN_PACKETS_PER_SEC', fallback='2')),
            'chat_max_pps': float(config.get('DEFAULT', 'CHAT_MAX_PACKETS_PER_SEC', fallback='20')),
            
            'vc_min_size': int(config.get('DEFAULT', 'VIDEO_CONF_MIN_SIZE', fallback='500')),
            'vc_max_size': int(config.get('DEFAULT', 'VIDEO_CONF_MAX_SIZE', fallback='1500')),
            'vc_min_pps': float(config.get('DEFAULT', 'VIDEO_CONF_MIN_PACKETS_PER_SEC', fallback='10')),
            'vc_bidir_ratio': float(config.get('DEFAULT', 'VIDEO_CONF_BIDIRECTIONAL_RATIO', fallback='0.3')),
            
            'scroll_min_avg': int(config.get('DEFAULT', 'SCROLL_MIN_AVG_SIZE', fallback='1500')),
            'scroll_dl_ratio': float(config.get('DEFAULT', 'SCROLL_DOWNLOAD_RATIO', fallback='0.8')),
            'scroll_burst_threshold': int(config.get('DEFAULT', 'SCROLL_BURST_THRESHOLD', fallback='5')),
            
            'analysis_interval': int(config.get('DEFAULT', 'ANALYSIS_INTERVAL', fallback='10'))
        }
    
    def is_local_ip(self, ip):
        """Check if IP is in local network"""
        for network in self.local_networks:
            if ip.startswith(network):
                return True
        return False
    
    def get_flow_key(self, src_ip, dst_ip):
        """Generate a unique key for a flow"""
        # Normalize the flow key so bidirectional traffic uses same key
        local_ip = None
        remote_ip = None
        
        if self.is_local_ip(src_ip):
            local_ip = src_ip
            remote_ip = dst_ip
        else:
            local_ip = dst_ip
            remote_ip = src_ip
        
        return f"{local_ip}:{remote_ip}"
    
    def process_packet(self, timestamp, src_ip, dst_ip, length):
        """Process a single packet"""
        flow_key = self.get_flow_key(src_ip, dst_ip)
        
        # Create new flow if it doesn't exist
        if flow_key not in self.flows:
            # Determine which is the local IP
            if self.is_local_ip(src_ip):
                self.flows[flow_key] = PacketFlow(src_ip, dst_ip)
            else:
                self.flows[flow_key] = PacketFlow(dst_ip, src_ip)
        
        # Add packet to flow
        self.flows[flow_key].add_packet(timestamp, src_ip, dst_ip, length)
    
    def classify_flow(self, flow):
        """Classify a flow as chat, video conference, or video scroll"""
        if len(flow.packets) < 5:
            return ActivityType.UNKNOWN
        
        avg_size = flow.get_average_packet_size()
        packet_rate = flow.get_packet_rate()
        bidir_ratio = flow.get_bidirectional_ratio()
        download_ratio = flow.get_download_ratio()
        is_bursty = flow.is_bursty(self.config['scroll_burst_threshold'])
        
        # Chat detection: small packets, moderate rate, bidirectional
        if (avg_size < self.config['chat_max_size'] and
            self.config['chat_min_pps'] <= packet_rate <= self.config['chat_max_pps'] and
            bidir_ratio > 0.2):
            return ActivityType.CHAT
        
        # Video conference: medium packets, high rate, strongly bidirectional
        if (self.config['vc_min_size'] <= avg_size <= self.config['vc_max_size'] and
            packet_rate >= self.config['vc_min_pps'] and
            bidir_ratio >= self.config['vc_bidir_ratio']):
            return ActivityType.VIDEO_CONFERENCE
        
        # Video scrolling: large packets, mostly download, bursty
        if (avg_size >= self.config['scroll_min_avg'] and
            download_ratio >= self.config['scroll_dl_ratio'] and
            is_bursty):
            return ActivityType.VIDEO_SCROLL
        
        return ActivityType.UNKNOWN
    
    def cleanup_old_flows(self, current_time):
        """Remove flows that haven't seen traffic recently"""
        to_remove = []
        
        for flow_key, flow in self.flows.items():
            if current_time - flow.last_time > self.flow_timeout:
                to_remove.append(flow_key)
        
        for flow_key in to_remove:
            del self.flows[flow_key]
    
    def analyze_flows(self):
        """Analyze all active flows and return classifications"""
        results = []
        
        for flow_key, flow in self.flows.items():
            classification = self.classify_flow(flow)
            
            results.append({
                'flow_key': flow_key,
                'src_ip': flow.src_ip,
                'dst_ip': flow.dst_ip,
                'classification': classification,
                'duration': flow.get_duration(),
                'packets': len(flow.packets),
                'bytes_up': flow.total_bytes_up,
                'bytes_down': flow.total_bytes_down,
                'avg_packet_size': flow.get_average_packet_size(),
                'packet_rate': flow.get_packet_rate(),
                'bidirectional_ratio': flow.get_bidirectional_ratio()
            })
        
        return results


def parse_packet_line(line):
    """Parse a line from packet log"""
    try:
        parts = line.strip().split('|')
        if len(parts) != 4:
            return None
        
        timestamp = float(parts[0])
        src_ip = parts[1].split(':')[0]  # Remove port if present
        dst_ip = parts[2].split(':')[0]
        length = int(parts[3])
        
        return timestamp, src_ip, dst_ip, length
    except (ValueError, IndexError):
        return None


def main():
    """Main analyzer loop"""
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <config_file> <packet_log>")
        sys.exit(1)
    
    config_file = sys.argv[1]
    packet_log = sys.argv[2]
    
    analyzer = TrafficAnalyzer(config_file)
    
    # Import and initialize database
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from database import InstaMonitorDB
    
    # Get data directory from config
    config = configparser.ConfigParser()
    config.read(config_file)
    data_dir = config.get('DEFAULT', 'DATA_DIR', fallback='/var/lib/instamonitor')
    
    db = InstaMonitorDB(data_dir)
    
    print("InstaMonitor Traffic Analyzer started")
    print(f"Config: {config_file}")
    print(f"Packet log: {packet_log}")
    print(f"Data directory: {data_dir}")
    
    last_analysis = time.time()
    
    # Follow the log file
    try:
        with open(packet_log, 'r') as f:
            # Move to end of file
            f.seek(0, 2)
            
            while True:
                line = f.readline()
                
                if not line:
                    # No new data, check if it's time to analyze
                    current_time = time.time()
                    
                    if current_time - last_analysis >= analyzer.config['analysis_interval']:
                        results = analyzer.analyze_flows()
                        
                        # Print results
                        print(f"\n=== Analysis at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===")
                        
                        activity_counts = defaultdict(int)
                        for result in results:
                            activity_counts[result['classification'].value] += 1
                            
                            if result['classification'] != ActivityType.UNKNOWN:
                                print(f"{result['src_ip']} -> {result['classification'].value}: "
                                      f"{result['duration']:.1f}s, {result['packets']} packets, "
                                      f"{result['bytes_down']/1024:.1f}KB down")
                                
                                # Save to database
                                try:
                                    db.record_flow_classification(
                                        device_ip=result['src_ip'],
                                        remote_ip=result['dst_ip'],
                                        platform=None,  # Will be determined from IP
                                        activity_type=result['classification'].value,
                                        duration=result['duration'],
                                        packet_count=result['packets'],
                                        bytes_up=result['bytes_up'],
                                        bytes_down=result['bytes_down'],
                                        avg_packet_size=result['avg_packet_size'],
                                        packet_rate=result['packet_rate'],
                                        bidirectional_ratio=result['bidirectional_ratio']
                                    )
                                except Exception as e:
                                    print(f"Warning: Failed to save to database: {e}", file=sys.stderr)
                        
                        print(f"\nActive flows: Chat={activity_counts['chat']}, "
                              f"Video Conf={activity_counts['video_conference']}, "
                              f"Video Scroll={activity_counts['video_scroll']}")
                        
                        analyzer.cleanup_old_flows(current_time)
                        last_analysis = current_time
                    
                    time.sleep(0.1)
                    continue
                
                # Process packet
                packet_data = parse_packet_line(line)
                if packet_data:
                    analyzer.process_packet(*packet_data)
    
    except KeyboardInterrupt:
        print("\nAnalyzer stopped")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
