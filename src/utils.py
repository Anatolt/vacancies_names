"""
Utility functions for browser automation, authentication, and messaging.
"""

import os
import json
import datetime
import hashlib
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, parse_qs

import requests
from playwright.async_api import Page, Browser, BrowserContext, Error


# Constants
LINKEDIN_LOGIN_URL = "https://www.linkedin.com/login"
LINKEDIN_PSETTINGS_URL = "https://www.linkedin.com/psettings/"
TIMEOUT = 6_000  # ms
STORAGE_STATE_FILE = "data/linkedin_auth.json"
DEBUG_DIR = "debug"


class BrowserClosedError(Exception):
    """Exception raised when the browser is detected to be closed."""
    pass


def print_ts(*args, **kwargs):
    """Print with timestamp."""
    now = datetime.datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
    print(now, *args, **kwargs)


def to_job_view_url(raw_url: str) -> str:
    """Convert LinkedIn search URL to job view URL if possible."""
    parsed = urlparse(raw_url)
    if "/jobs/search" in parsed.path and "linkedin.com" in parsed.netloc:
        q = parse_qs(parsed.query)
        job_id = q.get("currentJobId", [None])[0]
        if job_id and job_id.isdigit():
            return f"https://www.linkedin.com/jobs/view/{job_id}/"
    return raw_url


async def is_browser_alive(browser: Browser) -> bool:
    """Check if the browser is still running and not closed."""
    try:
        # Try to get a simple property from the browser
        # This will fail if the browser was closed
        is_connected = await browser.contexts[0].pages[0].evaluate("() => true")
        return True
    except (Error, IndexError, KeyError) as e:
        error_msg = str(e).lower()
        if "target page, context or browser has been closed" in error_msg or "connection closed" in error_msg:
            return False
        # If it's another type of error, the browser might still be alive
        return True


async def check_browser_or_abort(browser: Browser, debug: bool = False) -> None:
    """Check if browser is alive, raise a clear exception if not."""
    if not await is_browser_alive(browser):
        error_msg = "Browser has been closed manually. Aborting."
        if debug:
            print_ts(f"⚠️ DEBUG: {error_msg}")
        raise BrowserClosedError(error_msg)


def is_valid_auth_state(state_file: str) -> bool:
    """Check if the authentication state file is valid and contains cookies."""
    if not os.path.exists(state_file):
        return False
        
    try:
        with open(state_file, 'r') as f:
            state = json.load(f)
            
        # Check that we have cookies
        if not state.get('cookies') or len(state.get('cookies')) == 0:
            return False
            
        # Check for essential LinkedIn cookies
        linkedin_cookies = [c for c in state.get('cookies', []) 
                           if c.get('domain', '').endswith('linkedin.com')]
        
        # Look for critical cookies that indicate authentication
        auth_cookies = ['li_at', 'JSESSIONID', 'liap']
        has_auth_cookies = any(c.get('name') in auth_cookies for c in linkedin_cookies)
        
        # Check origins (less important but good to have)
        has_linkedin_origins = any('linkedin.com' in o.get('origin', '') 
                                 for o in state.get('origins', []))
                                 
        return has_auth_cookies or (len(linkedin_cookies) > 3 and has_linkedin_origins)
        
    except (json.JSONDecodeError, KeyError, FileNotFoundError) as e:
        print_ts(f"Error validating auth state file: {e}")
        return False


def setup_debug_dirs():
    """Create debug directory structure if it doesn't exist."""
    html_dir = Path(DEBUG_DIR) / "html"
    screenshots_dir = Path(DEBUG_DIR) / "screenshots"
    
    for dir_path in [html_dir, screenshots_dir]:
        dir_path.mkdir(parents=True, exist_ok=True)
        
    return html_dir, screenshots_dir


def get_debug_filename(url: str, attempt: int = 1) -> str:
    """Generate a consistent filename for debugging files."""
    # Create a hash of the URL to avoid filesystem issues with long URLs
    url_hash = hashlib.md5(url.encode()).hexdigest()[:10]
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Extract job ID if possible
    job_id = "unknown"
    if "/jobs/view/" in url:
        job_id = url.split("/jobs/view/")[1].split("/")[0]
    
    return f"{timestamp}_{job_id}_{url_hash}_attempt{attempt}"


async def save_debug_info(page: Page, url: str, html_content: str, debug_enabled: bool, attempt: int = 1) -> None:
    """Save debug information (HTML and screenshot) for a URL."""
    if not debug_enabled:
        return
    
    # Check if browser is still alive before attempting to save debug info
    try:
        if page.context.browser:
            alive = await is_browser_alive(page.context.browser)
            if not alive:
                print_ts(f"DEBUG: Browser closed before saving debug info for {url}")
                return
    except Exception as e:
        print_ts(f"DEBUG: Error checking browser state for debug: {e}")
        return
        
    html_dir, screenshots_dir = setup_debug_dirs()
    filename_base = get_debug_filename(url, attempt)
    
    # Save HTML
    html_path = html_dir / f"{filename_base}.html"
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    
    # Take and save screenshot
    screenshot_path = screenshots_dir / f"{filename_base}.png"
    try:
        await page.screenshot(path=screenshot_path)
        print_ts(f"Debug info saved: {html_path.name} and {screenshot_path.name}")
    except Exception as e:
        print_ts(f"Error taking screenshot: {e}")


def send_telegram_message(token: str, user_id: str, text: str) -> bool:
    """Send a message to a Telegram user via Bot API."""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": user_id,
        "text": text,
        "parse_mode": "HTML"
    }
    try:
        resp = requests.post(url, data=payload, timeout=10)
        if resp.status_code == 200:
            return True
        else:
            print_ts(f"Telegram API error: {resp.status_code} {resp.text}")
            return False
    except Exception as e:
        print_ts(f"Telegram send error: {e}")
        return False