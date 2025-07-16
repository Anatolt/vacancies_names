#!/usr/bin/env python3
"""
Collect Applied Jobs - Script to collect all LinkedIn Applied Jobs links

This script navigates through all pages of LinkedIn Applied Jobs and collects
all job links with progress saving and resume functionality.
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime
from dotenv import load_dotenv
from playwright.async_api import async_playwright

from src.utils import (
    print_ts, is_valid_auth_state, BrowserClosedError, STORAGE_STATE_FILE
)
from src.linkedin_auth import linkedin_login
from src.applied_jobs_parser import extract_all_applied_job_links, navigate_to_applied_jobs


def main():
    """Main entry point for the applied jobs collector."""
    load_dotenv()
    
    parser = argparse.ArgumentParser(description="Collect all LinkedIn Applied Jobs links")
    parser.add_argument("--output", help="Output file for job links (default: auto-generated)")
    parser.add_argument("--resume", help="Resume from existing file")
    parser.add_argument("--max-pages", type=int, default=50, help="Maximum pages to process (default: 50)")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    
    args = parser.parse_args()
    
    # Get credentials from environment
    email = os.getenv("LINKEDIN_EMAIL")
    password = os.getenv("LINKEDIN_PASSWORD")
    
    if not email or not password:
        print_ts("❌ LINKEDIN_EMAIL and LINKEDIN_PASSWORD must be set in .env file")
        sys.exit(1)
    
    # Setup output file
    if args.resume:
        output_file = args.resume
        print_ts(f"🔄 Resuming collection from: {output_file}")
    elif args.output:
        output_file = args.output
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"data/applied_jobs_links_{timestamp}.txt"
    
    print_ts(f"🚀 Starting Applied Jobs collection...")
    print_ts(f"📁 Output file: {output_file}")
    print_ts(f"📄 Max pages: {args.max_pages}")
    print_ts(f"🖥️ Headless mode: {'ON' if args.headless else 'OFF'}")
    
    # Run the collector
    try:
        asyncio.run(collect_applied_jobs(
            email=email,
            password=password,
            output_file=output_file,
            max_pages=args.max_pages,
            headless=args.headless
        ))
        
    except KeyboardInterrupt:
        print_ts("❌ Collection interrupted by user")
        print_ts(f"💾 Progress saved to: {output_file}")
        sys.exit(1)
    except Exception as e:
        print_ts(f"❌ Collection failed: {e}")
        sys.exit(1)


async def collect_applied_jobs(email: str, password: str, output_file: str, max_pages: int = 50, headless: bool = False):
    """
    Main function to collect all applied job links.
    
    Args:
        email: LinkedIn email
        password: LinkedIn password
        output_file: Path to output file
        max_pages: Maximum pages to process
        headless: Run browser in headless mode
    """
    try:
        async with async_playwright() as pw:
            try:
                browser = await pw.chromium.launch(headless=headless, slow_mo=50)
                
                # Create context with cookies if available
                if is_valid_auth_state(STORAGE_STATE_FILE):
                    context = await browser.new_context(storage_state=STORAGE_STATE_FILE)
                    print_ts(f"Using saved cookies from {STORAGE_STATE_FILE}")
                else:
                    context = await browser.new_context()
                    print_ts("Creating new context without cookies")
                
                page = await context.new_page()

                # Ensure LinkedIn login
                print_ts("🔐 Ensuring LinkedIn login...")
                try:
                    await linkedin_login(page, email, password)
                except BrowserClosedError:
                    print_ts("Browser was closed during login attempt. Aborting.")
                    return
                except Exception as login_error:
                    print_ts(f"Error during login: {login_error}")
                    return
                
                # Navigate to Applied Jobs page
                if not await navigate_to_applied_jobs(page):
                    print_ts("❌ Failed to navigate to Applied Jobs page")
                    return
                
                # Extract all job links with pagination
                print_ts("🔗 Starting collection of all applied job links...")
                job_links = await extract_all_applied_job_links(
                    page=page,
                    max_pages=max_pages,
                    resume_file=output_file
                )
                
                if job_links:
                    print_ts(f"🎉 Collection completed successfully!")
                    print_ts(f"📊 Total job links collected: {len(job_links)}")
                    print_ts(f"💾 Links saved to: {output_file}")
                    
                    # Show some sample links
                    print_ts("\n📋 Sample links:")
                    for i, link in enumerate(job_links[:5], 1):
                        print_ts(f"  {i}. {link}")
                    
                    if len(job_links) > 5:
                        print_ts(f"  ... and {len(job_links) - 5} more")
                    
                    print_ts(f"\n🔄 Next steps:")
                    print_ts(f"1. Use main.py to scrape job details:")
                    print_ts(f"   python main.py --links-file {output_file}")
                    print_ts(f"2. Or copy links to data/links.txt and run:")
                    print_ts(f"   python main.py")
                    
                else:
                    print_ts("⚠️ No job links were collected")

                await browser.close()
                
            except Exception as e:
                print_ts(f"Browser error: {e}")
                
    except Exception as e:
        print_ts(f"Playwright error: {e}")


if __name__ == "__main__":
    main()