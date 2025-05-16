#!/usr/bin/env python3
"""job_scraper_playwright.py – v2

Теперь вытягивает город/страну из LinkedIn‑страниц:
    • сначала ищет в явных селекторах (span.topcard__flavor--bullet)
    • если не нашёл, парсит hidden‑JSON и поле `"navigationBarSubtitle"`,
      где LinkedIn обычно кладёт строку вида «Company · Berlin, Germany (Hybrid)».

Также добавлено извлечение текста вакансии для последующего анализа на соответствие.
Включен режим отладки для сохранения HTML и скриншотов в папку debug/.
"""

from __future__ import annotations

import asyncio
import os
import re
import sys
import json
import argparse
import hashlib
import datetime
from pathlib import Path
from typing import List, Tuple, Dict, Optional, Any
from urllib.parse import urlparse, parse_qs

import pandas as pd
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from playwright.async_api import async_playwright, Page, Browser, BrowserContext, Error

LINKEDIN_LOGIN_URL = "https://www.linkedin.com/login"
LINKEDIN_PSETTINGS_URL = "https://www.linkedin.com/psettings/"
TIMEOUT = 6_000  # ms
STORAGE_STATE_FILE = "linkedin_auth.json"
DEBUG_DIR = "debug"

# -- Browser state handling functions --

class BrowserClosedError(Exception):
    """Exception raised when the browser is detected to be closed."""
    pass

async def is_browser_alive(browser: Browser) -> bool:
    """Check if the browser is still running and not closed.
    
    Args:
        browser: Playwright browser object
        
    Returns:
        bool: True if browser is still running, False if it was closed
    """
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
    """Check if browser is alive, raise a clear exception if not.
    
    Args:
        browser: Playwright browser object
        debug: Whether debug mode is enabled
        
    Raises:
        BrowserClosedError: If browser is detected to be closed
    """
    if not await is_browser_alive(browser):
        error_msg = "Browser has been closed manually. Aborting."
        if debug:
            print_ts(f"⚠️ DEBUG: {error_msg}")
        raise BrowserClosedError(error_msg)

# ─────────────────────────── helpers ───────────────────────────────────────────

def to_job_view_url(raw_url: str) -> str:
    parsed = urlparse(raw_url)
    if "/jobs/search" in parsed.path and "linkedin.com" in parsed.netloc:
        q = parse_qs(parsed.query)
        job_id = q.get("currentJobId", [None])[0]
        if job_id and job_id.isdigit():
            return f"https://www.linkedin.com/jobs/view/{job_id}/"
    return raw_url


def extract_linkedin(html: str) -> Tuple[str | None, str | None, str | None]:
    soup = BeautifulSoup(html, "html.parser")
    # ── title ────────────────────────────────────────────────────────────────
    title_tag = soup.select_one("h1.top-card-layout__title, h1[class*='_title']") or soup.find("h1")
    title = title_tag.get_text(strip=True) if title_tag else None

    # ── location: try visible span first ─────────────────────────────────────
    loc_tag = soup.select_one(
        "span.topcard__flavor--bullet, span.jobs-unified-top-card__subtitle-primary-grouping > span, [class*='_location']"
    )
    if loc_tag:
        location = loc_tag.get_text(strip=True)
    else:
        # ── fallback: hidden JSON chunk with \"navigationBarSubtitle\" ──
        m = re.search(r'"navigationBarSubtitle":"([^"]+)"|navigationBarSubtitle\\":\\"([^"]+)"' , html)
        location = None
        if m:
            subtitle = m.group(1) or m.group(2) # account for escaped quotes in JSON
            if subtitle:
                subtitle = subtitle.encode('utf-8').decode('unicode_escape') # handle unicode escapes
                parts = subtitle.split("·", 1)
                if len(parts) == 2:
                    loc_part = parts[1].strip()
                    # cut off parenthesis, e.g. "Germany (Remote)" → "Germany"
                    loc_part = re.sub(r"\s*\(.*?\)$", "", loc_part)
                    location = loc_part
    
    # ── description ────────────────────────────────────────────────────────────
    description = None
    # Try common LinkedIn job description selectors
    desc_selectors = [
        "div.description__text.description__text--rich", 
        "div.show-more-less-html",
        "section.description div.show-more-less-html",
        "div[class*='jobs-description']",
        "div[class*='jobs-box']",
        "section.description"
    ]
    
    for selector in desc_selectors:
        desc_element = soup.select_one(selector)
        if desc_element:
            # Don't include the "show more" button text
            for show_more in desc_element.select("button.show-more-less-html__button"):
                show_more.decompose()
            description = desc_element.get_text(strip=True, separator=' ')
            # If description is too short, it might not be the actual description
            if description and len(description) > 100:
                break
            
    # Fallback: try to extract from JSON data if available
    if not description or len(description) < 100:
        job_desc_pattern = r'"jobDescription":"([^"]+)"|jobDescription\\":\\"([^"]+)"'
        m = re.search(job_desc_pattern, html)
        if m:
            description = (m.group(1) or m.group(2)).encode('utf-8').decode('unicode_escape')
            
    # Make sure we don't grab location or metadata text as description
    if description and (
        (location and description.startswith(location)) or
        re.search(r'^\s*[\w\s]+,\s*[\w\s]+\s*·\s*\d+\s*days?\s*ago', description)
    ):
        description = None

    return title, location, description


def extract_generic(html: str) -> Tuple[str | None, str | None, str | None]:
    soup = BeautifulSoup(html, "html.parser")
    meta_title = soup.find("meta", property="og:title")
    title = meta_title["content"].strip() if meta_title and meta_title.get("content") else None
    if not title:
        h1 = soup.find("h1")
        if h1:
            title = h1.get_text(strip=True)
    
    location = None
    meta_loc = soup.find("meta", {"name": "job:location"})
    if meta_loc and meta_loc.get("content"):
        location = meta_loc["content"].strip()
    
    # Extract description
    description = None
    
    # Try meta description first
    meta_desc = soup.find("meta", {"name": "description", "property": "og:description"})
    if meta_desc and meta_desc.get("content"):
        description = meta_desc["content"].strip()
    
    # Try common job description containers
    if not description or len(description) < 100:  # If no meta description or too short
        desc_selectors = [
            "div.job-description", 
            "section.job-description",
            "div[class*='description']",
            "div[class*='job-details']",
            "div[id*='job-description']",
            "div[id*='description']",
            "article"
        ]
        
        for selector in desc_selectors:
            desc_elements = soup.select(selector)
            if desc_elements:
                # Use the one with most text
                best_elem = max(desc_elements, key=lambda x: len(x.get_text(strip=True)))
                candidate_desc = best_elem.get_text(strip=True, separator=' ')
                if len(candidate_desc) > 100 and len(candidate_desc) > len(description or ""):
                    description = candidate_desc
                    break
    
    # Make sure we don't grab location or metadata text as description
    if description and (
        (location and description.startswith(location)) or
        re.search(r'^\s*[\w\s]+,\s*[\w\s]+\s*·\s*\d+\s*days?\s*ago', description)
    ):
        description = None
        
    return title, location, description


def setup_debug_dirs():
    """Create debug directory structure if it doesn't exist"""
    html_dir = Path(DEBUG_DIR) / "html"
    screenshots_dir = Path(DEBUG_DIR) / "screenshots"
    
    for dir_path in [html_dir, screenshots_dir]:
        dir_path.mkdir(parents=True, exist_ok=True)
        
    return html_dir, screenshots_dir


def get_debug_filename(url: str, attempt: int = 1) -> str:
    """Generate a consistent filename for debugging files"""
    # Create a hash of the URL to avoid filesystem issues with long URLs
    url_hash = hashlib.md5(url.encode()).hexdigest()[:10]
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Extract job ID if possible
    job_id = "unknown"
    if "/jobs/view/" in url:
        job_id = url.split("/jobs/view/")[1].split("/")[0]
    
    return f"{timestamp}_{job_id}_{url_hash}_attempt{attempt}"


async def save_debug_info(page: Page, url: str, html_content: str, debug_enabled: bool, attempt: int = 1) -> None:
    """Save debug information (HTML and screenshot) for a URL"""
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


async def is_logged_in(page: Page) -> bool:
    """Check if user is logged in to LinkedIn
    
    Args:
        page: Playwright page object
        
    Returns:
        bool: True if logged in, False otherwise
    """
    print_ts(f"Checking login status by navigating to {LINKEDIN_PSETTINGS_URL}...")
    try:
        # Check browser alive before navigating
        if page.context.browser:
            await check_browser_or_abort(page.context.browser)
            
        try:
            await page.goto(LINKEDIN_PSETTINGS_URL, timeout=TIMEOUT, wait_until="networkidle")
        except Exception as e:
            print_ts(f"Error navigating to {LINKEDIN_PSETTINGS_URL} (networkidle): {str(e)[:150]}. Trying domcontentloaded...")
            
            # Check browser alive after first nav error
            if page.context.browser:
                await check_browser_or_abort(page.context.browser)
                
            try:
                await page.goto(LINKEDIN_PSETTINGS_URL, timeout=TIMEOUT, wait_until="domcontentloaded")
                await page.wait_for_timeout(3000) # Give some time for JS redirects
            except Exception as e2:
                print_ts(f"Error navigating to {LINKEDIN_PSETTINGS_URL} (domcontentloaded fallback): {str(e2)[:150]}. Assuming not logged in.")
                
                # Check browser alive after second nav error
                if page.context.browser:
                    await check_browser_or_abort(page.context.browser)
                return False

        current_url = page.url.lower()
        print_ts(f"Current URL after navigating to psettings: {current_url}")

        if "myaccount/settings" in current_url or "mypreferences/d/categories/account" in current_url:
            print_ts("✅ Login confirmed (URL indicates settings page).")
            return True
        
        # Check for common login page markers in URL
        login_url_markers = ["/login", "/uas/login", "/checkpoint/lg/login-submit"]
        if any(marker in current_url for marker in login_url_markers):
            print_ts("Login page URL detected. Not logged in.")
            return False

        # As a fallback, check for login form elements if URL is still psettings or similar non-confirmed state
        if LINKEDIN_PSETTINGS_URL.lower() in current_url or "linkedin.com/m/login" in current_url : # linkedin.com/m/login for mobile views
            login_form_selectors = ["input#username", "form.login__form", "button[type='submit'][aria-label*='Sign in']"]
            for selector in login_form_selectors:
                if await page.is_visible(selector):
                    print_ts(f"Login form element '{selector}' visible on {current_url}. Not logged in.")
                    return False
            print_ts(f"URL is {current_url}, but no definitive login form elements found. Checking for logged-in elements as a safeguard.")
            # Safeguard: if we are on psettings but don't see login form, and also don't see settings page, it's ambiguous.
            # For safety, assume not logged in unless we positively ID a settings page or a known logged-in element.
            # Example: Profile picture (though it might not be on psettings redirect before full load)
            if await page.is_visible("img.global-nav__me-photo"): # Check if profile pic is visible
                print_ts("Profile picture visible. Assuming logged in.")
                return True
            
            # Additional check for any of these common logged-in elements
            logged_in_selectors = [
                "div.feed-identity-module", # Feed identity module
                "li.global-nav__primary-item", # Nav bar items 
                "a[href^='/in/']", # Profile link
                "div[data-control-name='identity_welcome_message']" # Welcome message
            ]
            for selector in logged_in_selectors:
                if await page.is_visible(selector):
                    print_ts(f"Logged-in element '{selector}' visible. Assuming logged in.")
                    return True
        
        print_ts("Could not definitively confirm login status. Assuming not logged in for safety.")
        return False
    except BrowserClosedError:
        raise  # Re-raise to be caught by caller
    except Exception as e:
        print_ts(f"Error checking login status: {str(e)[:150]}. Assuming not logged in.")
        return False


def is_valid_auth_state(state_file: str) -> bool:
    """Check if the authentication state file is valid and contains cookies.
    
    Args:
        state_file: Path to the storage state file
        
    Returns:
        bool: True if valid, False otherwise
    """
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


def print_ts(*args, **kwargs):
    now = datetime.datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
    print(now, *args, **kwargs)


async def linkedin_login(page: Page, email: str, password: str, force_login: bool = False) -> None:
    """Log in to LinkedIn if not already logged in.
    
    Args:
        page: Playwright page object
        email: LinkedIn email
        password: LinkedIn password
        force_login: Force login even if auth file exists
        
    Raises:
        BrowserClosedError: If browser is closed during login
    """
    print_ts("Attempting to ensure LinkedIn session is active...")
    
    # Check browser alive before trying anything
    if page.context.browser:
        await check_browser_or_abort(page.context.browser)
    
    loaded_from_storage = False
    
    # Skip auth file if force_login is True
    if not force_login and is_valid_auth_state(STORAGE_STATE_FILE):
        print_ts("Auth state файл уже был подхвачен при создании контекста браузера.")
        loaded_from_storage = True
    elif os.path.exists(STORAGE_STATE_FILE) and not is_valid_auth_state(STORAGE_STATE_FILE):
        print_ts(f"Auth file '{STORAGE_STATE_FILE}' exists but appears invalid/empty. Will perform new login.")
    else:
        print_ts(f"Auth file '{STORAGE_STATE_FILE}' not found. Will perform new login.")

    # Check browser alive after loading storage
    if page.context.browser:
        await check_browser_or_abort(page.context.browser)

    if loaded_from_storage:
        try:
            if await is_logged_in(page):
                print_ts("✅ Session active (verified after loading from storage).")
                return
            else:
                print_ts("⚠️ Auth state loaded from file, but session appears inactive. Proceeding to manual login.")
        except BrowserClosedError:
            raise
    else: # If not loaded from storage, check if we are already logged in
        try:
            if await is_logged_in(page):
                print_ts("✅ Session active (verified without loading from storage - perhaps browser was already logged in).")
                # Save this "found" state for future use
                try:
                    await page.context.storage_state(path=STORAGE_STATE_FILE)
                    print_ts(f"✅ Saved detected authentication state to {STORAGE_STATE_FILE}")
                except Exception as e:
                    print_ts(f"⚠️ Error saving detected authentication state: {e}")
                return
        except BrowserClosedError:
            raise

    # Check browser alive before form login
    if page.context.browser:
        await check_browser_or_abort(page.context.browser)

    print_ts("Performing new login via form...")
    try:
        print_ts("Открываю страницу логина с ожиданием 'domcontentloaded' (таймаут 10 сек)...")
        await page.goto(LINKEDIN_LOGIN_URL, timeout=10000, wait_until="domcontentloaded")
        
        # Check browser alive after navigation
        if page.context.browser:
            await check_browser_or_abort(page.context.browser)
            
        # Check if we're actually on the login page
        if not await page.is_visible("input#username") and not await page.is_visible("form.login__form"):
            print_ts("Login page did not load properly or we're already logged in. Checking login status...")
            if await is_logged_in(page):
                print_ts("✅ Appears we're already logged in (login form not visible)")
                # Save this state
                try:
                    await page.context.storage_state(path=STORAGE_STATE_FILE)
                    print_ts(f"✅ Saved detected authentication state to {STORAGE_STATE_FILE}")
                except Exception as e:
                    print_ts(f"⚠️ Error saving detected authentication state: {e}")
                return
            else:
                print_ts("⚠️ Not logged in, but login form not found. This is unusual.")
                return
                
        print_ts("Ожидание появления поля username...")
        await page.wait_for_selector("input#username", state="visible", timeout=10000)
        print_ts("Ожидание появления поля password...")
        await page.wait_for_selector("input#password", state="visible", timeout=10000)
        # Clear fields first
        await page.fill("input#username", "")
        await page.fill("input#password", "")
        # Fill in credentials with a small delay between fields
        print_ts("Ввожу email...")
        await page.fill("input#username", email)
        await page.wait_for_timeout(500)
        print_ts("Ввожу пароль...")
        await page.fill("input#password", password)
        print_ts("Ожидание кнопки submit...")
        await page.wait_for_selector("button[type='submit']", state="visible", timeout=10000)
        print_ts("Нажимаю submit...")
        await page.click("button[type='submit']")
        print_ts("Жду появления признака успешного входа (аватарка или меню профиля) в течение 10 секунд...")
        try:
            await page.wait_for_selector("img.global-nav__me-photo, .global-nav__me", timeout=10000)
            print_ts("Обнаружен элемент профиля — вход успешен.")
        except Exception as e:
            print_ts(f"Не удалось обнаружить элемент профиля за 10 секунд: {e}")
        current_url = page.url
        print_ts(f"Текущий URL после логина: {current_url}")
        
        # Check browser alive after form submission
        if page.context.browser:
            await check_browser_or_abort(page.context.browser)
            
        # Wait for navigation to a page that indicates login (e.g., psettings redirect or feed)
        # is_logged_in itself navigates, so we can call it directly for verification.
        print_ts("Login form submitted. Verifying login status...")
    except BrowserClosedError:
        raise
    except Exception as e:
        print_ts(f"Error during login form submission: {e}. Login may have failed.")
        # Check if browser closed during this error
        if page.context.browser:
            if not await is_browser_alive(page.context.browser):
                raise BrowserClosedError("Browser closed during login form submission")
        # Even if form submission had an error, is_logged_in might still pass if a redirect happened quickly.

    # Final verification and save state
    try:
        if await is_logged_in(page):
            print_ts("Login successful after form submission (verified). Saving authentication state...")
            try:
                await page.context.storage_state(path=STORAGE_STATE_FILE)
                print_ts(f"✅ Saved authentication state to {STORAGE_STATE_FILE}")
            except Exception as e:
                print_ts(f"❌ Error saving authentication state: {e}")
            # debug: всегда сохраняем состояние после логина
            try:
                await page.context.storage_state(path="linkedin_auth_debug.json")
                print_ts("[DEBUG] Сохранил состояние куки в linkedin_auth_debug.json после логина.")
            except Exception as e:
                print_ts(f"[DEBUG] Не удалось сохранить debug-куки: {e}")
        else:
            print_ts(f"❌ Login verification failed after form submission. Auth state NOT saved.")
            # debug: сохраняем состояние даже при неудаче
            try:
                await page.context.storage_state(path="linkedin_auth_debug.json")
                print_ts("[DEBUG] Сохранил состояние куки в linkedin_auth_debug.json после НЕУДАЧНОГО логина.")
            except Exception as e:
                print_ts(f"[DEBUG] Не удалось сохранить debug-куки: {e}")
    except BrowserClosedError:
        raise


async def run_scraper(urls: List[str], email: str, password: str, output_csv: str, debug: bool = False):
    # Не создаём заголовок, просто очищаем файл
    open(output_csv, 'w', encoding='utf-8').close()
    
    if debug:
        # Create debug directories if they don't exist
        setup_debug_dirs()
        print_ts(f"Debug mode enabled - will save HTML and screenshots to {DEBUG_DIR}/")
    
    try:
        async with async_playwright() as pw:
            try:
                browser = await pw.chromium.launch(headless=False, slow_mo=50)
                # --- Исправление: создаём context с кукисами, если они валидны ---
                if is_valid_auth_state(STORAGE_STATE_FILE):
                    context = await browser.new_context(storage_state=STORAGE_STATE_FILE)
                    print_ts(f"Создаю контекст с сохранёнными кукисами из {STORAGE_STATE_FILE}.")
                else:
                    context = await browser.new_context()
                    print_ts("Создаю новый контекст без кукисов.")
                page = await context.new_page()

                # Initial login check/attempt if any LinkedIn URLs are present
                # This ensures that if we need to login, we do it once upfront if possible.
                if any("linkedin.com" in u for u in urls):
                    print_ts(f"LinkedIn URLs detected in list. Ensuring login status...")
                    try:
                        await linkedin_login(page, email, password) # This will login if not already logged in
                    except BrowserClosedError:
                        print_ts("Browser was closed during login attempt. Aborting.")
                        return
                    except Exception as login_error:
                        print_ts(f"Error during login: {login_error}")
                        if debug:
                            print_ts(f"DEBUG - Full login error: {login_error}")
                
                for raw_url_input in urls:
                    try:
                        # Check if browser is still alive before processing each URL
                        await check_browser_or_abort(browser, debug)
                        
                        url_to_scrape = to_job_view_url(raw_url_input)
                        print_ts(f"Processing URL: {url_to_scrape} (Original: {raw_url_input})")
                        html_content = None
                        title = None
                        loc = None
                        desc = None
                        is_linkedin_job_url = "linkedin.com" in urlparse(url_to_scrape).netloc and "/jobs/view/" in url_to_scrape

                        # --- First attempt to get content ---
                        print_ts(f"Attempt 1: Loading {url_to_scrape}...")
                        try:
                            await page.goto(url_to_scrape, timeout=TIMEOUT, wait_until="networkidle")
                            html_content = await page.content()
                            
                            # Save debug info for first attempt
                            if debug:
                                await save_debug_info(page, url_to_scrape, html_content, debug, attempt=1)
                                
                        except Exception as e1:
                            print_ts(f"Attempt 1: Error with networkidle for {url_to_scrape}: {str(e1)[:150]}. Retrying with 'load'...")
                            
                            # Check if browser closed after first error
                            if not await is_browser_alive(browser):
                                raise BrowserClosedError("Browser closed during page load")
                                
                            try:
                                await page.goto(url_to_scrape, timeout=TIMEOUT, wait_until="load")
                                await page.wait_for_timeout(2000) # Allow scripts to run after load
                                html_content = await page.content()
                                
                                # Save debug info for first attempt (load fallback)
                                if debug:
                                    await save_debug_info(page, url_to_scrape, html_content, debug, attempt=1)
                                    
                            except Exception as e2:
                                print_ts(f"Attempt 1: Error with 'load' for {url_to_scrape} as well: {str(e2)[:150]}")
                                # Check if browser closed during fallback attempt
                                if not await is_browser_alive(browser):
                                    raise BrowserClosedError("Browser closed during fallback page load")
                        
                        if html_content:
                            if is_linkedin_job_url:
                                title, loc, desc = extract_linkedin(html_content)
                            else:
                                title, loc, desc = extract_generic(html_content)
                            print_ts(f"Attempt 1: Extracted Title: '{title}', Location: '{loc}', Description: '{desc[:50] + '...' if desc else 'None'}'")

                        # --- Second attempt if first failed for LinkedIn URL and login might help ---
                        if is_linkedin_job_url and (not title or not loc or not desc):
                            print_ts(f"Attempt 1 for LinkedIn URL {url_to_scrape} yielded insufficient data (Title: '{title}', Loc: '{loc}', Desc: '{desc is not None}').")
                            print_ts("Ensuring login status again and retrying content extraction...")
                            
                            # Check if browser is still alive before login attempt
                            await check_browser_or_abort(browser, debug)
                            
                            try:
                                await linkedin_login(page, email, password) # Ensure we are logged in
                            except BrowserClosedError:
                                raise  # Re-raise to be caught by outer try/except
                            
                            # Check if browser is still alive after login
                            await check_browser_or_abort(browser, debug)
                            
                            print_ts(f"Attempt 2: Reloading {url_to_scrape} after login check...")
                            html_content_retry = None
                            try:
                                await page.goto(url_to_scrape, timeout=TIMEOUT, wait_until="networkidle")
                                html_content_retry = await page.content()
                                
                                # Save debug info for second attempt
                                if debug:
                                    await save_debug_info(page, url_to_scrape, html_content_retry, debug, attempt=2)
                                    
                            except Exception as e3:
                                print_ts(f"Attempt 2: Error with networkidle for {url_to_scrape}: {str(e3)[:150]}. Retrying with 'load'...")
                                
                                # Check if browser closed after retry error
                                if not await is_browser_alive(browser):
                                    raise BrowserClosedError("Browser closed during retry load")
                                    
                                try:
                                    await page.goto(url_to_scrape, timeout=TIMEOUT, wait_until="load")
                                    await page.wait_for_timeout(2000)
                                    html_content_retry = await page.content()
                                    
                                    # Save debug info for second attempt (load fallback)
                                    if debug:
                                        await save_debug_info(page, url_to_scrape, html_content_retry, debug, attempt=2)
                                        
                                except Exception as e4:
                                    print_ts(f"Attempt 2: Error with 'load' for {url_to_scrape} as well: {str(e4)[:150]}")
                                    # Check if browser closed during fallback retry
                                    if not await is_browser_alive(browser):
                                        raise BrowserClosedError("Browser closed during fallback retry")
                            
                            if html_content_retry:
                                html_content = html_content_retry # Use the new content
                                title_retry, loc_retry, desc_retry = extract_linkedin(html_content)
                                print_ts(f"Attempt 2: Extracted Title: '{title_retry}', Location: '{loc_retry}', Description: '{desc_retry[:50] + '...' if desc_retry else 'None'}'")
                                # Prefer retry results if they are better or original was None
                                title = title_retry if title_retry is not None else title
                                loc = loc_retry if loc_retry is not None else loc
                                desc = desc_retry if desc_retry is not None else desc
                            else:
                                print_ts(f"Attempt 2: Failed to get content for {url_to_scrape}.")
                        
                        # --- Conservative Interstitial Page Check (on the final html_content) ---
                        if html_content:
                            interstitial_keywords = ["please wait", "verifying", "are you human", "challenge", "too many requests", "before you continue", "verify you're human"]
                            current_page_text_lower = html_content.lower()
                            temp_soup = BeautifulSoup(html_content, "html.parser")
                            linkedin_title_selector = "h1.top-card-layout__title, h1[class*='_title']"
                            has_linkedin_job_title = temp_soup.select_one(linkedin_title_selector) is not None
                            
                            if (any(keyword in current_page_text_lower for keyword in interstitial_keywords) and
                                len(html_content) < 7000 and 
                                not has_linkedin_job_title):
                                print_ts(f"❌ Final content for {url_to_scrape} looks like an interstitial page. Recording as empty.")
                                html_content = None # This will lead to empty title/loc if not already set
                                title, loc, desc = None, None, None # Explicitly clear them
                        
                        # --- Save result ---
                        result = {"url": raw_url_input, "title": title, "location": loc, "description": desc}
                        pd.DataFrame([result]).to_csv(output_csv, mode='a', header=False, index=False, sep='\t')

                        if title or loc or desc:
                             print_ts(f"✅ Saved: '{title}' at '{loc}' with description length {len(desc) if desc else 0} (Original URL: {raw_url_input})")
                        elif html_content is None and not (title or loc or desc): # Explicitly None from interstitial or load failure
                             print_ts(f"⚠️ Saved EMPTY result for {raw_url_input} (failed to retrieve valid page content or was interstitial).")
                        else: # Content was parsed, but no title/loc found by extractors
                             print_ts(f"⚠️ Saved empty title/location/description for {raw_url_input} (content parsed, but no specific data found).")
                    
                    except BrowserClosedError as bce:
                        print_ts(f"⚠️ Browser was closed during processing of {raw_url_input}. Aborting.")
                        if debug:
                            print_ts(f"DEBUG - Browser closed error details: {bce}")
                        # Save empty result for the current URL
                        result = {"url": raw_url_input, "title": None, "location": None, "description": None}
                        pd.DataFrame([result]).to_csv(output_csv, mode='a', header=False, index=False, sep='\t')
                        print_ts(f"⚠️ Saved EMPTY result for {raw_url_input} (browser was closed manually).")
                        # Break the loop - don't process any more URLs
                        break
                
                print_ts("Closing browser.")
                try:
                    await browser.close()
                except Exception as close_error:
                    if debug:
                        print_ts(f"DEBUG - Error while closing browser (likely already closed): {close_error}")
                    
            except BrowserClosedError:
                print_ts("⚠️ Browser was closed manually during initialization. Aborting.")
            except Exception as browser_error:
                print_ts(f"❌ Error creating or using browser: {browser_error}")
                if debug:
                    print_ts(f"DEBUG - Full browser error: {browser_error}")
    
    except Exception as global_error:
        print_ts(f"❌ Global error in run_scraper: {global_error}")
        if debug:
            print_ts(f"DEBUG - Full global error: {global_error}")

def main():
    parser = argparse.ArgumentParser(description="LinkedIn job scraper")
    parser.add_argument("links_file", help="Text file with links to scrape")
    parser.add_argument("output_csv", help="Output CSV file")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode (save HTML and screenshots)")
    parser.add_argument("--force-login", action="store_true", help="Force new login, ignoring saved authentication")
    args = parser.parse_args()
    
    load_dotenv()
    email = os.getenv("LINKEDIN_EMAIL")
    password = os.getenv("LINKEDIN_PASSWORD")
    if not email or not password:
        print_ts("Set LINKEDIN_EMAIL / LINKEDIN_PASSWORD first!")
        sys.exit(1)

    with open(args.links_file, encoding="utf-8") as f:
        urls_from_file = [l.strip() for l in f if l.strip()]

    print_ts(f"Loaded {len(urls_from_file)} URLs…")
    
    if args.debug:
        print_ts("Debug mode enabled - will save HTML and screenshots to debug/")
    
    if args.force_login:
        print_ts("Force login enabled - will ignore saved authentication state")
    
    # Check auth file validity before running
    if os.path.exists(STORAGE_STATE_FILE):
        if is_valid_auth_state(STORAGE_STATE_FILE):
            print_ts(f"✅ Auth file {STORAGE_STATE_FILE} exists and appears valid.")
            if args.force_login:
                print_ts("🔔 Force login is enabled, so saved auth state will be ignored.")
        else:
            print_ts(f"⚠️ Auth file {STORAGE_STATE_FILE} exists but appears invalid/empty.")
            if not args.force_login:
                print_ts("Will attempt new login.")
    
    try:
        asyncio.run(run_scraper(urls_from_file, email, password, args.output_csv, debug=args.debug))
        print_ts(f"✅ Processing completed. Results saved to {args.output_csv}")
    except KeyboardInterrupt:
        print_ts("\n🛑 Process interrupted by user (Ctrl+C).")
        print_ts(f"⚠️ Results up to this point have been saved to {args.output_csv}")
    except Exception as e:
        print_ts(f"❌ Error during processing: {e}")
        print_ts(f"⚠️ Partial results may have been saved to {args.output_csv}")
        if args.debug:
            import traceback
            print_ts("Debug traceback:")
            traceback.print_exc()


if __name__ == "__main__":
    main()
