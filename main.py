#!/usr/bin/env python3
"""
Job Scraper - Main entry point

A tool for scraping job information from various job sites, with primary support for LinkedIn.
Supports debug mode for saving HTML and screenshots, history tracking to avoid duplicates,
and Telegram notifications.
"""

import argparse
import asyncio
import sys
from dotenv import load_dotenv
import os

from src.process_links import run_scraper, load_urls_from_file, send_completion_notification
from src.utils import print_ts


def main():
    """Main entry point for the job scraper."""
    load_dotenv()
    
    parser = argparse.ArgumentParser(description="Job scraper for LinkedIn and other job sites")
    parser.add_argument("--links-file", default="data/links.txt", help="File containing URLs to process")
    parser.add_argument("--output", default="data/results.csv", help="Output CSV file")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode (save HTML and screenshots)")
    parser.add_argument("--history", default="data/history.txt", help="History file to track processed URLs")
    
    args = parser.parse_args()
    
    # Get credentials from environment
    email = os.getenv("LINKEDIN_EMAIL")
    password = os.getenv("LINKEDIN_PASSWORD")
    telegram_token = os.getenv("TELEGRAM_TOKEN")
    telegram_user_id = os.getenv("TELEGRAM_USERID")
    
    if not email or not password:
        print_ts("❌ LINKEDIN_EMAIL and LINKEDIN_PASSWORD must be set in .env file")
        sys.exit(1)
    
    # Load URLs
    urls = load_urls_from_file(args.links_file)
    if not urls:
        print_ts("❌ No URLs found to process")
        sys.exit(1)
    
    print_ts(f"🚀 Starting job scraper...")
    print_ts(f"📁 Links file: {args.links_file}")
    print_ts(f"📄 Output file: {args.output}")
    print_ts(f"🐛 Debug mode: {'ON' if args.debug else 'OFF'}")
    print_ts(f"📚 History file: {args.history}")
    print_ts(f"🔗 URLs to process: {len(urls)}")
    
    # Run the scraper
    try:
        processed, skipped = asyncio.run(
            run_scraper(urls, email, password, args.output, args.debug, args.history)
        )
        
        print_ts(f"✅ Scraping completed!")
        print_ts(f"📊 Processed: {processed}")
        print_ts(f"⏭️ Skipped: {skipped}")
        
        # Send Telegram notification if configured
        if telegram_token and telegram_user_id:
            send_completion_notification(telegram_token, telegram_user_id, processed, skipped, args.output)
        
    except KeyboardInterrupt:
        print_ts("❌ Scraping interrupted by user")
        sys.exit(1)
    except Exception as e:
        print_ts(f"❌ Scraping failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()