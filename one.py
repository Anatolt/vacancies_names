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
from pathlib import Path
from typing import List, Tuple
from urllib.parse import urlparse, parse_qs

import pandas as pd
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from playwright.async_api import async_playwright, Page

LINKEDIN_LOGIN_URL = "https://www.linkedin.com/login"
TIMEOUT = 60_000  # ms

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
        m = re.search(r'"navigationBarSubtitle":"([^"]+)"', html)
        location = None
        if m:
            subtitle = m.group(1)
            # subtitle like "Company · Berlin, Germany (Remote)" or "Company · Germany (Remote)"
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


async def linkedin_login(page: Page, email: str, password: str) -> None:
    await page.goto(LINKEDIN_LOGIN_URL, timeout=TIMEOUT)
    await page.fill("input#username", email)
    await page.fill("input#password", password)
    await page.click("button[type='submit']")
    await page.wait_for_load_state("networkidle")


async def run_scraper(urls: List[str], email: str, password: str):
    results = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, slow_mo=50)
        context = await browser.new_context()
        page = await context.new_page()

        if any("linkedin.com" in u for u in urls):
            print("Logging in to LinkedIn…")
            await linkedin_login(page, email, password)

        for raw in urls:
            url = to_job_view_url(raw)
            print("→", url)
            try:
                await page.goto(url, timeout=TIMEOUT)
                await page.wait_for_load_state("domcontentloaded")
            except Exception as exc:
                print(f"❌ {exc}")
                results.append({"url": raw, "title": None, "location": None})
                continue

            html = await page.content()
            if "linkedin.com" in urlparse(url).netloc and "/jobs/view/" in url:
                title, loc = extract_linkedin(html)
            else:
                title, loc = extract_generic(html)
            results.append({"url": raw, "title": title, "location": loc})

        await browser.close()
    return results

# ───────────────────────────────── main ─────────────────────────────────────

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
        urls = [l.strip() for l in f if l.strip()]

    print(f"Loaded {len(urls)} URLs…")
    results = asyncio.run(run_scraper(urls, email, password))
    pd.DataFrame(results).to_csv(out_csv, index=False)
    print(f"✅ Saved {len(urls)} rows to {out_csv}")


if __name__ == "__main__":
    main()
