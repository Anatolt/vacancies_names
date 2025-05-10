#!/usr/bin/env python3
"""job_scraper_playwright.py – v2

Теперь вытягивает город/страну из LinkedIn‑страниц:
    • сначала ищет в явных селекторах (span.topcard__flavor--bullet)
    • если не нашёл, парсит hidden‑JSON и поле `"navigationBarSubtitle"`,
      где LinkedIn обычно кладёт строку вида «Company · Berlin, Germany (Hybrid)».

Остальная логика неизменна.
"""

from __future__ import annotations

import asyncio
import os
import re
import sys
import json
from pathlib import Path
from typing import List, Tuple, Dict
from urllib.parse import urlparse, parse_qs

import pandas as pd
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from playwright.async_api import async_playwright, Page

LINKEDIN_LOGIN_URL = "https://www.linkedin.com/login"
LINKEDIN_PSETTINGS_URL = "https://www.linkedin.com/psettings/"
TIMEOUT = 60_000  # ms
STORAGE_STATE_FILE = "linkedin_auth.json"

# ─────────────────────────── helpers ───────────────────────────────────────────

def to_job_view_url(raw_url: str) -> str:
    parsed = urlparse(raw_url)
    if "/jobs/search" in parsed.path and "linkedin.com" in parsed.netloc:
        q = parse_qs(parsed.query)
        job_id = q.get("currentJobId", [None])[0]
        if job_id and job_id.isdigit():
            return f"https://www.linkedin.com/jobs/view/{job_id}/"
    return raw_url


def extract_linkedin(html: str) -> Tuple[str | None, str | None]:
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

    return title, location


def extract_generic(html: str) -> Tuple[str | None, str | None]:
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
    return title, location


async def is_logged_in(page: Page) -> bool:
    print(f"Checking login status by navigating to {LINKEDIN_PSETTINGS_URL}...")
    try:
        await page.goto(LINKEDIN_PSETTINGS_URL, timeout=TIMEOUT, wait_until="networkidle")
    except Exception as e:
        print(f"Error navigating to {LINKEDIN_PSETTINGS_URL} (networkidle): {str(e)[:150]}. Trying domcontentloaded...")
        try:
            await page.goto(LINKEDIN_PSETTINGS_URL, timeout=TIMEOUT, wait_until="domcontentloaded")
            await page.wait_for_timeout(3000) # Give some time for JS redirects
        except Exception as e2:
            print(f"Error navigating to {LINKEDIN_PSETTINGS_URL} (domcontentloaded fallback): {str(e2)[:150]}. Assuming not logged in.")
            return False

    current_url = page.url.lower()
    print(f"Current URL after navigating to psettings: {current_url}")

    if "myaccount/settings" in current_url or "mypreferences/d/categories/account" in current_url:
        print("✅ Login confirmed (URL indicates settings page).")
        return True
    
    # Check for common login page markers in URL
    login_url_markers = ["/login", "/uas/login", "/checkpoint/lg/login-submit"]
    if any(marker in current_url for marker in login_url_markers):
        print("Login page URL detected. Not logged in.")
        return False

    # As a fallback, check for login form elements if URL is still psettings or similar non-confirmed state
    if LINKEDIN_PSETTINGS_URL.lower() in current_url or "linkedin.com/m/login" in current_url : # linkedin.com/m/login for mobile views
        login_form_selectors = ["input#username", "form.login__form", "button[type='submit'][aria-label*='Sign in']"]
        for selector in login_form_selectors:
            if await page.is_visible(selector):
                print(f"Login form element '{selector}' visible on {current_url}. Not logged in.")
                return False
        print(f"URL is {current_url}, but no definitive login form elements found. Checking for logged-in elements as a safeguard.")
        # Safeguard: if we are on psettings but don't see login form, and also don't see settings page, it's ambiguous.
        # For safety, assume not logged in unless we positively ID a settings page or a known logged-in element.
        # Example: Profile picture (though it might not be on psettings redirect before full load)
        if await page.is_visible("img.global-nav__me-photo"): # Check if profile pic is visible
             print("Profile picture visible. Assuming logged in.")
             return True
    
    print("Could not definitively confirm login status. Assuming not logged in for safety.")
    return False


async def linkedin_login(page: Page, email: str, password: str) -> None:
    print("Attempting to ensure LinkedIn session is active...")
    loaded_from_storage = False
    if os.path.exists(STORAGE_STATE_FILE):
        try:
            with open(STORAGE_STATE_FILE, 'r') as f:
                storage_content = f.read()
            if storage_content and storage_content.strip() != '{"cookies": [], "origins": []}':
                state = json.loads(storage_content)
                if state.get('cookies') and len(state.get('cookies')) > 0:
                    print("Attempting to load auth state from file...")
                    await page.context.storage_state(path=STORAGE_STATE_FILE)
                    print("Auth state supposedly loaded from file.")
                    loaded_from_storage = True
                else:
                    print(f"Auth file '{STORAGE_STATE_FILE}' found but seems invalid. Will perform new login if needed.")
            else:
                print(f"Auth file '{STORAGE_STATE_FILE}' is empty/placeholder. Will perform new login if needed.")
        except Exception as e:
            print(f"Could not load/parse auth state from '{STORAGE_STATE_FILE}': {e}. Will perform new login if needed.")
    else:
        print(f"Auth file '{STORAGE_STATE_FILE}' not found. Will perform new login if needed.")

    if loaded_from_storage:
        if await is_logged_in(page):
            print("✅ Session active (verified after loading from storage).")
            return
        else:
            print("⚠️ Auth state loaded from file, but session appears inactive. Proceeding to manual login.")
    else: # If not loaded from storage, check if by some miracle we are already logged in
        if await is_logged_in(page):
            print("✅ Session active (verified without loading from storage - perhaps browser was already logged in).")
            # Potentially save this "found" state?
            # For now, let's not, to keep it simple. If it was important, next run will save it after form login.
            return

    print("Performing new login via form...")
    try:
        await page.goto(LINKEDIN_LOGIN_URL, timeout=TIMEOUT, wait_until="networkidle")
        await page.fill("input#username", email)
        await page.fill("input#password", password)
        print("Submitting login form...")
        await page.click("button[type='submit']")
        # Wait for navigation to a page that indicates login (e.g., psettings redirect or feed)
        # is_logged_in itself navigates, so we can call it directly for verification.
        print("Login form submitted. Verifying login status...")
    except Exception as e:
        print(f"Error during login form submission: {e}. Login may have failed.")
        # Even if form submission had an error, is_logged_in might still pass if a redirect happened quickly.

    if await is_logged_in(page):
        print("Login successful after form submission (verified). Saving authentication state...")
        try:
            await page.context.storage_state(path=STORAGE_STATE_FILE)
            print(f"✅ Saved authentication state to {STORAGE_STATE_FILE}")
        except Exception as e:
            print(f"❌ Error saving authentication state: {e}")
    else:
        print(f"❌ Login verification failed after form submission. Auth state NOT saved.")


async def run_scraper(urls: List[str], email: str, password: str, output_csv: str):
    pd.DataFrame(columns=["url", "title", "location"]).to_csv(output_csv, index=False)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, slow_mo=50)
        context = await browser.new_context()
        page = await context.new_page()

        # Initial login check/attempt if any LinkedIn URLs are present
        # This ensures that if we need to login, we do it once upfront if possible.
        if any("linkedin.com" in u for u in urls):
            print("LinkedIn URLs detected in list. Ensuring login status...")
            await linkedin_login(page, email, password) # This will login if not already logged in

        for raw_url_input in urls:
            url_to_scrape = to_job_view_url(raw_url_input)
            print(f"Processing URL: {url_to_scrape} (Original: {raw_url_input})")
            html_content = None
            title = None
            loc = None
            is_linkedin_job_url = "linkedin.com" in urlparse(url_to_scrape).netloc and "/jobs/view/" in url_to_scrape

            # --- First attempt to get content ---
            print(f"Attempt 1: Loading {url_to_scrape}...")
            try:
                await page.goto(url_to_scrape, timeout=TIMEOUT, wait_until="networkidle")
                html_content = await page.content()
            except Exception as e1:
                print(f"Attempt 1: Error with networkidle for {url_to_scrape}: {str(e1)[:150]}. Retrying with 'load'...")
                try:
                    await page.goto(url_to_scrape, timeout=TIMEOUT, wait_until="load")
                    await page.wait_for_timeout(2000) # Allow scripts to run after load
                    html_content = await page.content()
                except Exception as e2:
                    print(f"Attempt 1: Error with 'load' for {url_to_scrape} as well: {str(e2)[:150]}")
            
            if html_content:
                if is_linkedin_job_url:
                    title, loc = extract_linkedin(html_content)
                else:
                    title, loc = extract_generic(html_content)
                print(f"Attempt 1: Extracted Title: '{title}', Location: '{loc}'")

            # --- Second attempt if first failed for LinkedIn URL and login might help ---
            if is_linkedin_job_url and (not title or not loc):
                print(f"Attempt 1 for LinkedIn URL {url_to_scrape} yielded insufficient data (Title: '{title}', Loc: '{loc}').")
                print("Ensuring login status again and retrying content extraction...")
                await linkedin_login(page, email, password) # Ensure we are logged in
                
                print(f"Attempt 2: Reloading {url_to_scrape} after login check...")
                html_content_retry = None
                try:
                    await page.goto(url_to_scrape, timeout=TIMEOUT, wait_until="networkidle")
                    html_content_retry = await page.content()
                except Exception as e3:
                    print(f"Attempt 2: Error with networkidle for {url_to_scrape}: {str(e3)[:150]}. Retrying with 'load'...")
                    try:
                        await page.goto(url_to_scrape, timeout=TIMEOUT, wait_until="load")
                        await page.wait_for_timeout(2000)
                        html_content_retry = await page.content()
                    except Exception as e4:
                        print(f"Attempt 2: Error with 'load' for {url_to_scrape} as well: {str(e4)[:150]}")
                
                if html_content_retry:
                    html_content = html_content_retry # Use the new content
                    title_retry, loc_retry = extract_linkedin(html_content)
                    print(f"Attempt 2: Extracted Title: '{title_retry}', Location: '{loc_retry}'")
                    # Prefer retry results if they are better or original was None
                    if title_retry is not None or loc_retry is not None:
                         title, loc = title_retry, loc_retry 
                else:
                    print(f"Attempt 2: Failed to get content for {url_to_scrape}.")
            
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
                    print(f"❌ Final content for {url_to_scrape} looks like an interstitial page. Recording as empty.")
                    html_content = None # This will lead to empty title/loc if not already set
                    title, loc = None, None # Explicitly clear them
            
            # --- Save result ---
            result = {"url": raw_url_input, "title": title, "location": loc}
            pd.DataFrame([result]).to_csv(output_csv, mode='a', header=False, index=False)

            if title or loc:
                 print(f"✅ Saved: '{title}' at '{loc}' (Original URL: {raw_url_input})")
            elif html_content is None and not (title or loc): # Explicitly None from interstitial or load failure
                 print(f"⚠️ Saved EMPTY result for {raw_url_input} (failed to retrieve valid page content or was interstitial).")
            else: # Content was parsed, but no title/loc found by extractors
                 print(f"⚠️ Saved empty title/location for {raw_url_input} (content parsed, but no specific data found).")
        
        print("Closing browser.")
        await browser.close()

def main():
    if len(sys.argv) != 3:
        print(f"Usage: {Path(sys.argv[0]).name} <links.txt> <output.csv>")
        sys.exit(1)

    links_file, out_csv = sys.argv[1:3]
    load_dotenv()
    email = os.getenv("LINKEDIN_EMAIL")
    password = os.getenv("LINKEDIN_PASSWORD")
    if not email or not password:
        print("Set LINKEDIN_EMAIL / LINKEDIN_PASSWORD first!")
        sys.exit(1)

    with open(links_file, encoding="utf-8") as f:
        urls_from_file = [l.strip() for l in f if l.strip()]

    print(f"Loaded {len(urls_from_file)} URLs…")
    asyncio.run(run_scraper(urls_from_file, email, password, out_csv))
    print(f"✅ Processing completed. Results saved to {out_csv}")


if __name__ == "__main__":
    main()
