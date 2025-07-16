"""
Applied Jobs Parser - Extract job links from LinkedIn Applied Jobs page

This module handles parsing of LinkedIn's "My Jobs" (Applied) page to extract
job URLs with support for pagination.
"""

import asyncio
import os
import re
from typing import List, Set, Tuple
from urllib.parse import urlparse, parse_qs
from playwright.async_api import Page

from src.utils import print_ts, BrowserClosedError


APPLIED_JOBS_URL = "https://www.linkedin.com/my-items/saved-jobs/?cardType=APPLIED"


async def extract_job_links_from_page(page: Page) -> List[str]:
    """
    Extract job links from the current applied jobs page.
    
    Args:
        page: Playwright page object
        
    Returns:
        List of job URLs found on the current page
    """
    try:
        # Wait for job cards to load
        await page.wait_for_selector('a[href*="jobs/view/"]', timeout=10000)
        
        # Extract all job links with the applied jobs tracking parameter
        job_links = await page.evaluate('''
            () => {
                // Try multiple selectors to find job links
                const selectors = [
                    'a[href*="jobs/view/"][trk*="flagship3_job_home_appliedjobs"]',
                    'a[href*="jobs/view/"]',
                    'a[trk*="flagship3_job_home_appliedjobs"]'
                ];
                
                let allLinks = [];
                let debugInfo = [];
                
                for (const selector of selectors) {
                    const links = Array.from(document.querySelectorAll(selector));
                    const hrefs = links
                        .map(link => link.href)
                        .filter(href => href && href.includes('jobs/view/'));
                    
                    debugInfo.push(`Selector "${selector}": found ${links.length} elements, ${hrefs.length} job links`);
                    
                    if (hrefs.length > 0) {
                        allLinks = allLinks.concat(hrefs);
                        break; // Use the first selector that finds links
                    }
                }
                
                // Additional debug: check what elements exist
                const allJobLinks = Array.from(document.querySelectorAll('a[href*="jobs/view/"]'));
                debugInfo.push(`Total job links on page: ${allJobLinks.length}`);
                
                // Log debug info to console
                console.log('Debug info:', debugInfo);
                
                return {
                    links: allLinks,
                    debug: debugInfo
                };
            }
        ''')
        
        # Print debug information
        if 'debug' in job_links:
            for debug_line in job_links['debug']:
                print_ts(f"🐛 {debug_line}")
            job_links = job_links['links']
        elif isinstance(job_links, dict) and 'links' in job_links:
            job_links = job_links['links']
        
        # Clean and deduplicate URLs
        clean_links = []
        seen_job_ids = set()
        
        for link in job_links:
            # Extract job ID from URL
            match = re.search(r'/jobs/view/(\d+)/', link)
            if match:
                job_id = match.group(1)
                if job_id not in seen_job_ids:
                    # Create clean URL without tracking parameters
                    clean_url = f"https://www.linkedin.com/jobs/view/{job_id}/"
                    clean_links.append(clean_url)
                    seen_job_ids.add(job_id)
        
        return clean_links
        
    except Exception as e:
        print_ts(f"Error extracting job links: {e}")
        return []


async def check_for_more_jobs(page: Page) -> bool:
    """
    Check if there are more jobs to load (pagination).
    
    Args:
        page: Playwright page object
        
    Returns:
        True if there are more jobs to load, False otherwise
    """
    try:
        # Scroll to bottom to make sure pagination is visible
        await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
        await asyncio.sleep(2)
        
        # Look for "Next" button in pagination
        next_button_selectors = [
            'button[aria-label="Next"]',
            'button[aria-label*="Next"]',
            'button:has-text("Next")',
            '.artdeco-pagination__button--next',
            'button[data-test-pagination-page-btn="next"]'
        ]
        
        for selector in next_button_selectors:
            try:
                element = await page.query_selector(selector)
                if element:
                    is_visible = await element.is_visible()
                    is_enabled = await element.is_enabled()
                    if is_visible and is_enabled:
                        print_ts(f"Found Next button: {selector}")
                        return True
            except:
                continue
        
        # Look for numbered pagination buttons (2, 3, 4, etc.)
        # Find the current active page and check if there's a next page
        pagination_info = await page.evaluate('''
            () => {
                // Look for pagination container
                const paginationSelectors = [
                    '.artdeco-pagination',
                    '[role="navigation"]',
                    '.pagination'
                ];
                
                let paginationContainer = null;
                for (const selector of paginationSelectors) {
                    paginationContainer = document.querySelector(selector);
                    if (paginationContainer) break;
                }
                
                if (!paginationContainer) {
                    return { hasNext: false, currentPage: 1, totalPages: 1 };
                }
                
                // Find current page (usually has aria-current="page" or is highlighted)
                const currentPageElement = paginationContainer.querySelector('[aria-current="page"], .active, .selected');
                const currentPage = currentPageElement ? parseInt(currentPageElement.textContent) || 1 : 1;
                
                // Find all page number buttons
                const pageButtons = Array.from(paginationContainer.querySelectorAll('button, a'))
                    .filter(btn => /^\d+$/.test(btn.textContent.trim()));
                
                const pageNumbers = pageButtons.map(btn => parseInt(btn.textContent)).filter(num => !isNaN(num));
                const maxPage = Math.max(...pageNumbers, currentPage);
                
                // Check if there's a next page button or a higher page number
                const hasNextButton = !!paginationContainer.querySelector('button[aria-label*="Next"], button:has-text("Next")');
                const hasHigherPage = pageNumbers.some(num => num > currentPage);
                
                return {
                    hasNext: hasNextButton || hasHigherPage,
                    currentPage: currentPage,
                    totalPages: maxPage,
                    availablePages: pageNumbers
                };
            }
        ''')
        
        print_ts(f"Pagination info: Current page {pagination_info['currentPage']}, Total pages {pagination_info['totalPages']}")
        print_ts(f"Available pages: {pagination_info['availablePages']}")
        
        return pagination_info['hasNext']
        
    except Exception as e:
        print_ts(f"Error checking for more jobs: {e}")
        return False


async def load_more_jobs(page: Page) -> bool:
    """
    Attempt to load more jobs by clicking pagination buttons.
    
    Args:
        page: Playwright page object
        
    Returns:
        True if more jobs were loaded successfully, False otherwise
    """
    try:
        # Scroll to bottom to make sure pagination is visible
        await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
        await asyncio.sleep(1)
        
        # First, try to click "Next" button
        next_button_selectors = [
            'button[aria-label="Next"]',
            'button[aria-label*="Next"]',
            'button:has-text("Next")',
            '.artdeco-pagination__button--next'
        ]
        
        for selector in next_button_selectors:
            try:
                element = await page.query_selector(selector)
                if element:
                    is_visible = await element.is_visible()
                    is_enabled = await element.is_enabled()
                    if is_visible and is_enabled:
                        print_ts(f"Clicking Next button: {selector}")
                        await element.click()
                        await asyncio.sleep(4)  # Wait for page to load
                        return True
            except Exception as e:
                print_ts(f"Error clicking Next button {selector}: {e}")
                continue
        
        # If no Next button, try to find the next page number
        next_page_result = await page.evaluate('''
            () => {
                // Look for pagination container
                const paginationSelectors = [
                    '.artdeco-pagination',
                    '[role="navigation"]',
                    '.pagination'
                ];
                
                let paginationContainer = null;
                for (const selector of paginationSelectors) {
                    paginationContainer = document.querySelector(selector);
                    if (paginationContainer) break;
                }
                
                if (!paginationContainer) {
                    return { success: false, reason: 'No pagination container found' };
                }
                
                // Find current page
                const currentPageElement = paginationContainer.querySelector('[aria-current="page"], .active, .selected');
                const currentPage = currentPageElement ? parseInt(currentPageElement.textContent) || 1 : 1;
                
                // Find next page button
                const nextPageNumber = currentPage + 1;
                const nextPageButton = paginationContainer.querySelector(`button:has-text("${nextPageNumber}"), a:has-text("${nextPageNumber}")`);
                
                if (nextPageButton && !nextPageButton.disabled) {
                    nextPageButton.click();
                    return { success: true, nextPage: nextPageNumber };
                }
                
                return { success: false, reason: `No next page button found for page ${nextPageNumber}` };
            }
        ''')
        
        if next_page_result['success']:
            print_ts(f"Clicked page number: {next_page_result['nextPage']}")
            await asyncio.sleep(4)  # Wait for page to load
            return True
        else:
            print_ts(f"Could not find next page: {next_page_result['reason']}")
            return False
        
    except Exception as e:
        print_ts(f"Error loading more jobs: {e}")
        return False


async def get_total_jobs_count(page: Page) -> int:
    """
    Try to extract the total number of applied jobs from the page.
    
    Args:
        page: Playwright page object
        
    Returns:
        Total number of jobs if found, 0 otherwise
    """
    try:
        # Look for total count in various places
        count_selectors = [
            '.workflow-results-container h1',  # "My Jobs" heading area
            '.search-results-container__text',
            '.jobs-search-results-list__text',
            '[data-test-id*="count"]'
        ]
        
        for selector in count_selectors:
            try:
                element = await page.query_selector(selector)
                if element:
                    text = await element.inner_text()
                    # Look for numbers in the text
                    numbers = re.findall(r'\d+', text)
                    if numbers:
                        return int(numbers[0])
            except:
                continue
        
        # Fallback: count job cards on page
        job_cards = await page.query_selector_all('a[href*="jobs/view/"][trk="flagship3_job_home_appliedjobs"]')
        return len(job_cards)
        
    except Exception as e:
        print_ts(f"Error getting total jobs count: {e}")
        return 0


def load_existing_links(links_file: str) -> Tuple[List[str], Set[str]]:
    """
    Load existing job links from file to resume extraction.
    
    Args:
        links_file: Path to the links file
        
    Returns:
        Tuple of (list of links, set of job IDs)
    """
    existing_links = []
    seen_job_ids = set()
    
    if os.path.exists(links_file):
        try:
            with open(links_file, 'r', encoding='utf-8') as f:
                for line in f:
                    link = line.strip()
                    if link and 'jobs/view/' in link:
                        existing_links.append(link)
                        # Extract job ID
                        match = re.search(r'/jobs/view/(\d+)/', link)
                        if match:
                            seen_job_ids.add(match.group(1))
            
            print_ts(f"📂 Loaded {len(existing_links)} existing links from {links_file}")
        except Exception as e:
            print_ts(f"⚠️ Error loading existing links: {e}")
    
    return existing_links, seen_job_ids


def save_links_to_file(links: List[str], links_file: str) -> None:
    """
    Save job links to file.
    
    Args:
        links: List of job links
        links_file: Path to save the links
    """
    try:
        os.makedirs(os.path.dirname(links_file), exist_ok=True)
        with open(links_file, 'w', encoding='utf-8') as f:
            for link in links:
                f.write(f"{link}\n")
        print_ts(f"💾 Saved {len(links)} links to {links_file}")
    except Exception as e:
        print_ts(f"❌ Error saving links: {e}")


def append_links_to_file(new_links: List[str], links_file: str) -> None:
    """
    Append new job links to file.
    
    Args:
        new_links: List of new job links to append
        links_file: Path to the links file
    """
    try:
        os.makedirs(os.path.dirname(links_file), exist_ok=True)
        with open(links_file, 'a', encoding='utf-8') as f:
            for link in new_links:
                f.write(f"{link}\n")
        print_ts(f"💾 Appended {len(new_links)} new links to {links_file}")
    except Exception as e:
        print_ts(f"❌ Error appending links: {e}")


async def extract_all_applied_job_links(page: Page, max_pages: int = 10, resume_file: str = None) -> List[str]:
    """
    Extract all job links from LinkedIn Applied Jobs page with pagination support.
    
    Args:
        page: Playwright page object (should be on applied jobs page)
        max_pages: Maximum number of pages to process (safety limit)
        resume_file: Path to file for saving/resuming progress
        
    Returns:
        List of all unique job URLs from applied jobs
    """
    from datetime import datetime
    import os
    
    # Setup resume file
    if not resume_file:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        resume_file = f"debug/applied/applied_jobs_links_{timestamp}.txt"
    
    # Load existing links if resuming
    all_job_links, seen_job_ids = load_existing_links(resume_file)
    page_count = 0
    
    print_ts("🔍 Starting extraction of applied job links...")
    print_ts(f"💾 Progress will be saved to: {resume_file}")
    
    if all_job_links:
        print_ts(f"🔄 Resuming extraction - already have {len(all_job_links)} links")
    
    try:
        # Get initial total count estimate
        total_estimate = await get_total_jobs_count(page)
        if total_estimate > 0:
            print_ts(f"📊 Estimated total applied jobs: {total_estimate}")
        
        while page_count < max_pages:
            page_count += 1
            print_ts(f"📄 Processing page {page_count}...")
            
            # Wait for page to load
            await asyncio.sleep(2)
            
            # Extract job links from current page
            page_links = await extract_job_links_from_page(page)
            
            if not page_links:
                print_ts("⚠️ No job links found on current page")
                break
            
            # Add new unique links
            new_links_for_page = []
            new_links_count = 0
            
            for link in page_links:
                # Extract job ID to check for duplicates
                match = re.search(r'/jobs/view/(\d+)/', link)
                if match:
                    job_id = match.group(1)
                    if job_id not in seen_job_ids:
                        clean_url = f"https://www.linkedin.com/jobs/view/{job_id}/"
                        all_job_links.append(clean_url)
                        new_links_for_page.append(clean_url)
                        seen_job_ids.add(job_id)
                        new_links_count += 1
            
            print_ts(f"✅ Found {new_links_count} new job links on page {page_count}")
            print_ts(f"📈 Total unique jobs collected: {len(all_job_links)}")
            
            # Save new links immediately after each page
            if new_links_for_page:
                if page_count == 1 and not os.path.exists(resume_file):
                    # First page - create new file
                    save_links_to_file(all_job_links, resume_file)
                else:
                    # Subsequent pages - append new links
                    append_links_to_file(new_links_for_page, resume_file)
            
            # Check if there are more jobs to load
            if not await check_for_more_jobs(page):
                print_ts("🏁 No more jobs to load - pagination complete")
                break
            
            # Load more jobs
            if not await load_more_jobs(page):
                print_ts("⚠️ Failed to load more jobs - stopping pagination")
                break
            
            # Safety check: if we haven't found new links in the last iteration
            if new_links_count == 0:
                print_ts("⚠️ No new links found - might have reached the end")
                break
    
    except KeyboardInterrupt:
        print_ts("⏸️ Extraction interrupted by user")
        print_ts(f"💾 Progress saved to: {resume_file}")
        print_ts(f"📊 Collected {len(all_job_links)} links so far")
        raise
    except BrowserClosedError:
        print_ts("❌ Browser was closed during extraction")
        print_ts(f"💾 Progress saved to: {resume_file}")
        raise
    except Exception as e:
        print_ts(f"❌ Error during applied jobs extraction: {e}")
        print_ts(f"💾 Progress saved to: {resume_file}")
    
    print_ts(f"🎉 Applied jobs extraction completed!")
    print_ts(f"📊 Total unique job links extracted: {len(all_job_links)}")
    print_ts(f"💾 Final results saved to: {resume_file}")
    
    return all_job_links


async def navigate_to_applied_jobs(page: Page) -> bool:
    """
    Navigate to the LinkedIn Applied Jobs page.
    
    Args:
        page: Playwright page object
        
    Returns:
        True if navigation was successful, False otherwise
    """
    try:
        print_ts(f"🌐 Navigating to Applied Jobs page...")
        await page.goto(APPLIED_JOBS_URL, timeout=15000, wait_until="domcontentloaded")
        
        # Wait for the page to load
        await asyncio.sleep(3)
        
        # Verify we're on the right page
        current_url = page.url
        if "my-items/saved-jobs" in current_url and "cardType=APPLIED" in current_url:
            print_ts("✅ Successfully navigated to Applied Jobs page")
            return True
        else:
            print_ts(f"⚠️ Unexpected URL after navigation: {current_url}")
            return False
            
    except Exception as e:
        print_ts(f"❌ Error navigating to Applied Jobs page: {e}")
        return False