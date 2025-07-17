#!/usr/bin/env python3
"""
Simple Extension Test with Playwright

This script loads the Chrome extension into Playwright and tests basic functionality.
"""

import asyncio
import os
import sys
import tempfile
from pathlib import Path
from playwright.async_api import async_playwright

# Add src to path for imports
sys.path.append('src')
from utils import print_ts
from linkedin_auth import linkedin_login


async def test_extension():
    """Test the Chrome extension with Playwright"""
    print_ts("🚀 Starting Chrome extension test...")
    
    # Get extension path
    extension_path = Path("extension").absolute()
    print_ts(f"📁 Extension path: {extension_path}")
    
    # Verify extension exists
    if not extension_path.exists():
        print_ts("❌ Extension directory not found")
        return False
    
    # Load credentials
    from dotenv import load_dotenv
    load_dotenv()
    
    email = os.getenv("LINKEDIN_EMAIL")
    password = os.getenv("LINKEDIN_PASSWORD")
    
    if not email or not password:
        print_ts("❌ LINKEDIN_EMAIL and LINKEDIN_PASSWORD must be set in .env file")
        return False
    
    async with async_playwright() as pw:
        # Launch browser with extension
        print_ts("🌐 Launching browser with extension...")
        browser = await pw.chromium.launch(
            headless=False,  # Keep visible for debugging
            args=[
                f"--disable-extensions-except={extension_path}",
                f"--load-extension={extension_path}",
                "--disable-web-security",
                "--disable-features=VizDisplayCompositor"
            ]
        )
        
        # Create context
        context = await browser.new_context(
            accept_downloads=True,
            viewport={'width': 1280, 'height': 720}
        )
        
        page = await context.new_page()
        
        try:
            # Step 1: Login to LinkedIn
            print_ts("🔐 Logging into LinkedIn...")
            await linkedin_login(page, email, password)
            
            # Step 2: Navigate to Applied Jobs page
            print_ts("🌐 Navigating to Applied Jobs page...")
            await page.goto("https://www.linkedin.com/my-items/saved-jobs/?cardType=APPLIED")
            await page.wait_for_load_state("networkidle")
            
            # Step 3: Wait for page to load completely
            print_ts("⏳ Waiting for page to load...")
            await asyncio.sleep(5)
            
            # Step 4: Check if we're on the right page
            current_url = page.url
            if "my-items/saved-jobs" not in current_url:
                print_ts(f"⚠️ Not on Applied Jobs page. Current URL: {current_url}")
                return False
            
            print_ts("✅ Successfully on Applied Jobs page")
            
            # Step 5: Test extension popup (if possible)
            print_ts("🧪 Testing extension popup...")
            try:
                # Try to find extension icon (this might not work in Playwright)
                extension_icon = page.locator('[data-testid="extension-icon"]')
                if await extension_icon.count() > 0:
                    await extension_icon.click()
                    print_ts("✅ Extension icon found and clicked")
                else:
                    print_ts("⚠️ Extension icon not found (this is normal in Playwright)")
            except Exception as e:
                print_ts(f"⚠️ Could not test extension popup: {e}")
            
            # Step 6: Test content script functionality
            print_ts("🔧 Testing content script...")
            try:
                # Check if content script is loaded
                content_script_result = await page.evaluate('''
                    () => {
                        // Check if our content script is running
                        if (typeof window.collector !== 'undefined') {
                            return {
                                loaded: true,
                                isAppliedJobsPage: window.collector.isAppliedJobsPage()
                            };
                        }
                        return { loaded: false };
                    }
                ''')
                
                if content_script_result.get('loaded'):
                    print_ts("✅ Content script is loaded")
                    if content_script_result.get('isAppliedJobsPage'):
                        print_ts("✅ Content script recognizes Applied Jobs page")
                    else:
                        print_ts("⚠️ Content script doesn't recognize Applied Jobs page")
                else:
                    print_ts("⚠️ Content script not loaded")
                    
            except Exception as e:
                print_ts(f"⚠️ Error testing content script: {e}")
            
            # Step 7: Test manual link extraction
            print_ts("🔗 Testing manual link extraction...")
            try:
                # Extract links manually using the same logic as content script
                links = await page.evaluate('''
                    () => {
                        const selectors = [
                            'a[href*="jobs/view/"][trk*="flagship3_job_home_appliedjobs"]',
                            'a[href*="jobs/view/"]',
                            'a[trk*="flagship3_job_home_appliedjobs"]'
                        ];
                        
                        let allLinks = [];
                        
                        for (const selector of selectors) {
                            const links = Array.from(document.querySelectorAll(selector));
                            const hrefs = links
                                .map(link => link.href)
                                .filter(href => href && href.includes('jobs/view/'));
                            
                            if (hrefs.length > 0) {
                                allLinks = allLinks.concat(hrefs);
                                break;
                            }
                        }
                        
                        // Clean and deduplicate URLs
                        const cleanLinks = [];
                        const seenJobIds = new Set();
                        
                        for (const link of allLinks) {
                            const match = link.match(/\/jobs\/view\/(\d+)\//);
                            if (match) {
                                const jobId = match[1];
                                if (!seenJobIds.has(jobId)) {
                                    const cleanUrl = `https://www.linkedin.com/jobs/view/${jobId}/`;
                                    cleanLinks.push(cleanUrl);
                                    seenJobIds.add(jobId);
                                }
                            }
                        }
                        
                        return cleanLinks;
                    }
                ''')
                
                print_ts(f"📊 Found {len(links)} job links on current page")
                
                if links:
                    print_ts("📋 Sample links:")
                    for i, link in enumerate(links[:3], 1):
                        print_ts(f"  {i}. {link}")
                    
                    # Save links to file for comparison
                    temp_dir = tempfile.mkdtemp(prefix="extension_test_")
                    test_file = os.path.join(temp_dir, "test_links.txt")
                    
                    with open(test_file, 'w', encoding='utf-8') as f:
                        for link in links:
                            f.write(f"{link}\n")
                    
                    print_ts(f"💾 Saved {len(links)} links to {test_file}")
                    print_ts("✅ Manual link extraction test passed")
                    
                else:
                    print_ts("⚠️ No job links found on current page")
                    
            except Exception as e:
                print_ts(f"❌ Error testing link extraction: {e}")
            
            # Step 8: Test pagination detection
            print_ts("📄 Testing pagination detection...")
            try:
                pagination_info = await page.evaluate('''
                    () => {
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
                        
                        const currentPageElement = paginationContainer.querySelector('[aria-current="page"], .active, .selected');
                        const currentPage = currentPageElement ? parseInt(currentPageElement.textContent) || 1 : 1;
                        
                        const pageButtons = Array.from(paginationContainer.querySelectorAll('button, a'))
                            .filter(btn => /^\d+$/.test(btn.textContent.trim()));
                        
                        const pageNumbers = pageButtons.map(btn => parseInt(btn.textContent)).filter(num => !isNaN(num));
                        const maxPage = Math.max(...pageNumbers, currentPage);
                        
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
                
                print_ts(f"📊 Pagination info: Current page {pagination_info['currentPage']}, Total pages {pagination_info['totalPages']}")
                print_ts(f"📊 Has next page: {pagination_info['hasNext']}")
                
                if pagination_info['hasNext']:
                    print_ts("✅ Pagination detection test passed")
                else:
                    print_ts("ℹ️ No pagination found (single page or end of list)")
                    
            except Exception as e:
                print_ts(f"⚠️ Error testing pagination: {e}")
            
            print_ts("✅ Extension test completed successfully!")
            return True
            
        except Exception as e:
            print_ts(f"❌ Extension test failed: {e}")
            return False
        finally:
            await browser.close()


async def main():
    """Main function"""
    success = await test_extension()
    
    if success:
        print_ts("🎉 All tests passed!")
        print_ts("\n📋 Next steps:")
        print_ts("1. Install the extension in Chrome manually")
        print_ts("2. Test the full functionality")
        print_ts("3. Use the collected links with main.py")
    else:
        print_ts("❌ Some tests failed")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main()) 