"""
History management utilities.
"""

import json
import os
from datetime import datetime
from typing import Dict, Any, List
from src.utils import print_ts


def migrate_old_history(old_history_path: str, new_history_path: str = None) -> None:
    """
    Migrate old plain-text history file to new JSON format.
    
    Args:
        old_history_path: Path to old history file (plain URLs)
        new_history_path: Path for new history file (defaults to same path with .json extension)
    """
    if not os.path.exists(old_history_path):
        print_ts(f"Old history file not found: {old_history_path}")
        return
    
    if new_history_path is None:
        new_history_path = old_history_path.replace('.txt', '_migrated.txt')
    
    print_ts(f"Migrating history from {old_history_path} to {new_history_path}")
    
    migrated_count = 0
    
    try:
        with open(old_history_path, 'r', encoding='utf-8') as old_file:
            with open(new_history_path, 'w', encoding='utf-8') as new_file:
                for line in old_file:
                    url = line.strip()
                    if url:
                        # Create JSON entry for old URL
                        entry = {
                            'url': url,
                            'title': None,
                            'location': None,
                            'description': None,
                            'processed_at': datetime.now().isoformat(),
                            'migrated_from_old_format': True
                        }
                        new_file.write(json.dumps(entry, ensure_ascii=False) + '\n')
                        migrated_count += 1
        
        print_ts(f"✅ Successfully migrated {migrated_count} entries")
        print_ts(f"Old file: {old_history_path}")
        print_ts(f"New file: {new_history_path}")
        
    except Exception as e:
        print_ts(f"❌ Error during migration: {e}")


def view_history(history_path: str, limit: int = 10) -> None:
    """
    Display recent history entries in a readable format.
    
    Args:
        history_path: Path to history file
        limit: Number of recent entries to show
    """
    if not os.path.exists(history_path):
        print_ts(f"History file not found: {history_path}")
        return
    
    entries = []
    
    try:
        with open(history_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                
                try:
                    data = json.loads(line)
                    entries.append(data)
                except json.JSONDecodeError:
                    # Handle old format
                    entries.append({
                        'url': line,
                        'title': 'N/A (old format)',
                        'location': 'N/A',
                        'description': 'N/A',
                        'processed_at': 'Unknown'
                    })
        
        print_ts(f"\n📚 History Overview ({len(entries)} total entries)")
        print_ts("=" * 80)
        
        # Show most recent entries
        recent_entries = entries[-limit:] if len(entries) > limit else entries
        
        for i, entry in enumerate(reversed(recent_entries), 1):
            print_ts(f"\n{i}. {entry.get('title', 'No title')}")
            print_ts(f"   📍 {entry.get('location', 'No location')}")
            print_ts(f"   🔗 {entry.get('url', 'No URL')}")
            print_ts(f"   ⏰ {entry.get('processed_at', 'Unknown time')}")
            
            if entry.get('description'):
                desc = entry['description'][:100] + "..." if len(entry['description']) > 100 else entry['description']
                print_ts(f"   📝 {desc}")
        
        if len(entries) > limit:
            print_ts(f"\n... and {len(entries) - limit} more entries")
            
    except Exception as e:
        print_ts(f"❌ Error reading history: {e}")


def search_history(history_path: str, query: str) -> List[Dict[str, Any]]:
    """
    Search history entries by title, location, or description.
    
    Args:
        history_path: Path to history file
        query: Search query (case-insensitive)
        
    Returns:
        List of matching entries
    """
    if not os.path.exists(history_path):
        print_ts(f"History file not found: {history_path}")
        return []
    
    matches = []
    query_lower = query.lower()
    
    try:
        with open(history_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                
                try:
                    data = json.loads(line)
                    
                    # Search in title, location, and description
                    searchable_text = ' '.join([
                        data.get('title', ''),
                        data.get('location', ''),
                        data.get('description', '')
                    ]).lower()
                    
                    if query_lower in searchable_text:
                        matches.append(data)
                        
                except json.JSONDecodeError:
                    # Handle old format
                    if query_lower in line.lower():
                        matches.append({
                            'url': line,
                            'title': 'N/A (old format)',
                            'location': 'N/A',
                            'description': 'N/A',
                            'processed_at': 'Unknown'
                        })
        
        print_ts(f"🔍 Found {len(matches)} matches for '{query}'")
        return matches
        
    except Exception as e:
        print_ts(f"❌ Error searching history: {e}")
        return []


def get_history_stats(history_path: str) -> Dict[str, Any]:
    """
    Get statistics about the history file.
    
    Args:
        history_path: Path to history file
        
    Returns:
        Dictionary with statistics
    """
    if not os.path.exists(history_path):
        return {'error': 'History file not found'}
    
    stats = {
        'total_entries': 0,
        'successful_parses': 0,
        'failed_parses': 0,
        'linkedin_jobs': 0,
        'other_sites': 0,
        'oldest_entry': None,
        'newest_entry': None
    }
    
    try:
        with open(history_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                
                stats['total_entries'] += 1
                
                try:
                    data = json.loads(line)
                    
                    # Count successful vs failed parses
                    if data.get('title'):
                        stats['successful_parses'] += 1
                    else:
                        stats['failed_parses'] += 1
                    
                    # Count LinkedIn vs other sites
                    url = data.get('url', '')
                    if 'linkedin.com' in url:
                        stats['linkedin_jobs'] += 1
                    else:
                        stats['other_sites'] += 1
                    
                    # Track date range
                    processed_at = data.get('processed_at')
                    if processed_at:
                        if not stats['oldest_entry'] or processed_at < stats['oldest_entry']:
                            stats['oldest_entry'] = processed_at
                        if not stats['newest_entry'] or processed_at > stats['newest_entry']:
                            stats['newest_entry'] = processed_at
                            
                except json.JSONDecodeError:
                    # Old format entry
                    stats['failed_parses'] += 1
                    if 'linkedin.com' in line:
                        stats['linkedin_jobs'] += 1
                    else:
                        stats['other_sites'] += 1
        
        return stats
        
    except Exception as e:
        return {'error': f'Error reading history: {e}'}