#!/usr/bin/env python3
"""
History Manager - Utility for managing comprehensive job scraping history.

Usage:
    python history_manager.py view [--limit 10]
    python history_manager.py search "android developer"
    python history_manager.py stats
    python history_manager.py migrate data/history.txt
"""

import argparse
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from history_utils import view_history, search_history, get_history_stats, migrate_old_history
from utils import print_ts


def main():
    parser = argparse.ArgumentParser(description="Manage job scraping history")
    parser.add_argument("--history", default="data/history.txt", help="Path to history file")
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # View command
    view_parser = subparsers.add_parser('view', help='View recent history entries')
    view_parser.add_argument('--limit', type=int, default=10, help='Number of entries to show')
    
    # Search command
    search_parser = subparsers.add_parser('search', help='Search history entries')
    search_parser.add_argument('query', help='Search query')
    
    # Stats command
    subparsers.add_parser('stats', help='Show history statistics')
    
    # Migrate command
    migrate_parser = subparsers.add_parser('migrate', help='Migrate old history format to new JSON format')
    migrate_parser.add_argument('old_file', help='Path to old history file')
    migrate_parser.add_argument('--output', help='Output file (optional)')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    if args.command == 'view':
        view_history(args.history, args.limit)
        
    elif args.command == 'search':
        matches = search_history(args.history, args.query)
        if matches:
            print_ts(f"\n📋 Search Results:")
            print_ts("=" * 60)
            for i, entry in enumerate(matches, 1):
                print_ts(f"\n{i}. {entry.get('title', 'No title')}")
                print_ts(f"   📍 {entry.get('location', 'No location')}")
                print_ts(f"   🔗 {entry.get('url', 'No URL')}")
                print_ts(f"   ⏰ {entry.get('processed_at', 'Unknown time')}")
        else:
            print_ts("No matches found.")
            
    elif args.command == 'stats':
        stats = get_history_stats(args.history)
        if 'error' in stats:
            print_ts(f"❌ {stats['error']}")
        else:
            print_ts(f"\n📊 History Statistics")
            print_ts("=" * 40)
            print_ts(f"Total entries: {stats['total_entries']}")
            print_ts(f"Successful parses: {stats['successful_parses']}")
            print_ts(f"Failed parses: {stats['failed_parses']}")
            print_ts(f"LinkedIn jobs: {stats['linkedin_jobs']}")
            print_ts(f"Other sites: {stats['other_sites']}")
            if stats['oldest_entry']:
                print_ts(f"Oldest entry: {stats['oldest_entry']}")
            if stats['newest_entry']:
                print_ts(f"Newest entry: {stats['newest_entry']}")
                
    elif args.command == 'migrate':
        migrate_old_history(args.old_file, args.output)


if __name__ == '__main__':
    main()