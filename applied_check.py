#!/usr/bin/env python3
"""
Applied Jobs Checker - Script to analyze LinkedIn Applied Jobs page

This script opens the LinkedIn Applied Jobs page, saves a screenshot and HTML
to understand the page structure for future parsing.
"""

import asyncio
import os
import sys
from datetime import datetime
from dotenv import load_dotenv
from playwright.async_api import async_playwright

from src.utils import (
    print_ts, is_valid_auth_state, setup_debug_dirs, 
    BrowserClosedError, STORAGE_STATE_FILE
)
from src.linkedin_auth import linkedin_login
from src.applied_jobs_parser import extract_all_applied_job_links, navigate_to_applied_jobs


APPLIED_JOBS_URL = "https://www.linkedin.com/my-items/saved-jobs/?cardType=APPLIED"


async def save_applied_page_info(page, debug_dir: str = "debug/applied"):
    """Save screenshot and HTML of the applied jobs page."""
    try:
        # Ensure debug directory exists
        os.makedirs(debug_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save screenshot
        screenshot_path = f"{debug_dir}/applied_jobs_{timestamp}.png"
        await page.screenshot(path=screenshot_path, full_page=True)
        print_ts(f"📸 Screenshot saved: {screenshot_path}")
        
        # Save HTML
        html_content = await page.content()
        html_path = f"{debug_dir}/applied_jobs_{timestamp}.html"
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        print_ts(f"📄 HTML saved: {html_path}")
        
        # Save page info
        info_path = f"{debug_dir}/applied_jobs_{timestamp}_info.txt"
        with open(info_path, 'w', encoding='utf-8') as f:
            f.write(f"URL: {page.url}\n")
            f.write(f"Title: {await page.title()}\n")
            f.write(f"Timestamp: {timestamp}\n")
            f.write(f"Screenshot: {screenshot_path}\n")
            f.write(f"HTML: {html_path}\n")
        print_ts(f"ℹ️ Info saved: {info_path}")
        
        return screenshot_path, html_path, info_path
        
    except Exception as e:
        print_ts(f"❌ Error saving applied page info: {e}")
        return None, None, None


async def check_applied_jobs():
    """Main function to check applied jobs page."""
    load_dotenv()
    
    # Get credentials from environment
    email = os.getenv("LINKEDIN_EMAIL")
    password = os.getenv("LINKEDIN_PASSWORD")
    
    if not email or not password:
        print_ts("❌ LINKEDIN_EMAIL and LINKEDIN_PASSWORD must be set in .env file")
        sys.exit(1)
    
    print_ts(f"🚀 Starting Applied Jobs checker...")
    print_ts(f"🔗 Target URL: {APPLIED_JOBS_URL}")
    
    try:
        async with async_playwright() as pw:
            try:
                browser = await pw.chromium.launch(headless=False, slow_mo=50)
                
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
                print_ts(f"🌐 Navigating to Applied Jobs page...")
                await page.goto(APPLIED_JOBS_URL, timeout=15000, wait_until="domcontentloaded")
                
                # Wait for page to load completely
                print_ts("⏳ Waiting for page to load...")
                await page.wait_for_timeout(5000)  # Wait 5 seconds for dynamic content
                
                # Try to wait for some common elements that might indicate the page is loaded
                try:
                    # Wait for either job cards or "no jobs" message
                    await page.wait_for_selector('div[data-test-id], .jobs-search-no-results, .artdeco-empty-state', timeout=10000)
                except:
                    print_ts("⚠️ Timeout waiting for specific elements, but continuing...")
                
                print_ts(f"📄 Current page title: {await page.title()}")
                print_ts(f"🔗 Current URL: {page.url}")
                
                # Save page information
                print_ts("💾 Saving page information...")
                screenshot_path, html_path, info_path = await save_applied_page_info(page)
                
                if screenshot_path and html_path:
                    print_ts("✅ Applied Jobs page analysis completed!")
                    print_ts(f"📸 Screenshot: {screenshot_path}")
                    print_ts(f"📄 HTML: {html_path}")
                    print_ts(f"ℹ️ Info: {info_path}")
                else:
                    print_ts("❌ Failed to save page information")
                
                # Extract all applied job links with full pagination
                print_ts("\n🔗 Extracting ALL Applied Job Links...")
                try:
                    job_links = await extract_all_applied_job_links(page, max_pages=10)
                    
                    if job_links:
                        print_ts(f"🎉 Parser test successful!")
                        print_ts(f"📊 Found {len(job_links)} applied job links:")
                        
                        # Save links to file
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        links_file = f"debug/applied/applied_jobs_links_{timestamp}.txt"
                        with open(links_file, 'w', encoding='utf-8') as f:
                            for i, link in enumerate(job_links, 1):
                                f.write(f"{link}\n")
                                if i <= 5:  # Show first 5 in console
                                    print_ts(f"  {i}. {link}")
                        
                        if len(job_links) > 5:
                            print_ts(f"  ... and {len(job_links) - 5} more")
                        
                        print_ts(f"💾 All links saved to: {links_file}")
                        print_ts("\n🔍 Next steps:")
                        print_ts("1. Use these links with the existing scraper")
                        print_ts("2. Add LLM analysis for job matching")
                        print_ts("3. Integrate with Google Sheets")
                        
                    else:
                        print_ts("⚠️ Parser test failed - no job links found")
                        
                except Exception as parser_error:
                    print_ts(f"❌ Parser test failed: {parser_error}")

                # Keep browser open for manual inspection
                print_ts("\n⏸️ Browser will stay open for manual inspection.")
                print_ts("Press Ctrl+C to close and exit.")
                
                try:
                    # Keep the script running until user interrupts
                    while True:
                        await asyncio.sleep(1)
                except KeyboardInterrupt:
                    print_ts("👋 Closing browser...")

                await browser.close()
                
            except Exception as e:
                print_ts(f"Browser error: {e}")
                
    except Exception as e:
        print_ts(f"Playwright error: {e}")


def main():
    """Entry point for the applied jobs checker."""
    try:
        asyncio.run(check_applied_jobs())
    except KeyboardInterrupt:
        print_ts("❌ Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print_ts(f"❌ Failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()