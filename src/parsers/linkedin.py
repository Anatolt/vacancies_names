"""
LinkedIn job parser module.
"""

import re
from typing import Tuple, Optional
from bs4 import BeautifulSoup


def extract_linkedin(html: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Extract job information from LinkedIn job page HTML.
    
    Args:
        html: Raw HTML content of LinkedIn job page
        
    Returns:
        Tuple of (title, location, description)
    """
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