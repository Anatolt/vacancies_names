"""
Generic job parser for non-LinkedIn websites.
"""

import re
from typing import Tuple, Optional
from bs4 import BeautifulSoup


def extract_generic(html: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Extract job information from generic job page HTML.
    
    Args:
        html: Raw HTML content of job page
        
    Returns:
        Tuple of (title, location, description)
    """
    soup = BeautifulSoup(html, "html.parser")
    
    # Extract title
    meta_title = soup.find("meta", property="og:title")
    title = meta_title["content"].strip() if meta_title and meta_title.get("content") else None
    if not title:
        h1 = soup.find("h1")
        if h1:
            title = h1.get_text(strip=True)
    
    # Extract location
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