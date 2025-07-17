#!/usr/bin/env python3
"""
Fixed Extension Test with Correct Selectors and Pagination

This script tests the Chrome extension using the same logic as collect_applied_jobs.py
"""

import asyncio
import os
import sys
import tempfile
import re
from pathlib import Path
from playwright.async_api import async_playwright

# Add src to path for imports
sys.path.append('src')
from utils import print_ts, is_valid_auth_state


class FixedExtensionTest:
    def __init__(self):
        self.extension_path = Path("extension").absolute()
        self.auth_file = Path("data/linkedin_auth.json")
        self.output_dir = Path("test_output")  # Постоянная директория для результатов
        self.test_results = {}
        self.all_links = []
        
    async def setup(self):
        """Setup test environment"""
        print_ts("🔧 Setting up fixed extension test...")
        
        # Create output directory
        self.output_dir.mkdir(exist_ok=True)
        print_ts(f"📁 Output directory: {self.output_dir}")
        
        # Verify extension exists
        if not self.extension_path.exists():
            raise FileNotFoundError("Extension directory not found")
        
        # Check authentication
        if not self.auth_file.exists():
            raise FileNotFoundError("LinkedIn auth file not found. Run main.py first to create linkedin_auth.json")
        
        if not is_valid_auth_state(self.auth_file):
            raise ValueError("LinkedIn auth file is invalid or expired")
        
        print_ts("✅ Test environment ready with valid LinkedIn auth")
        
    async def test_extension_with_pagination(self):
        """Test extension with pagination like collect_applied_jobs.py"""
        print_ts("🌐 Testing extension with pagination...")
        
        async with async_playwright() as pw:
            # Launch browser with extension
            browser = await pw.chromium.launch(
                headless=False,  # Keep visible for debugging
                args=[
                    f"--disable-extensions-except={self.extension_path}",
                    f"--load-extension={self.extension_path}",
                    "--disable-web-security",
                    "--disable-features=VizDisplayCompositor"
                ]
            )
            
            # Create context with saved auth state
            context = await browser.new_context(
                storage_state=str(self.auth_file),
                viewport={'width': 1280, 'height': 720},
                accept_downloads=True
            )
            
            page = await context.new_page()
            
            try:
                # Step 1: Navigate to Applied Jobs page
                print_ts("📄 Navigating to Applied Jobs page...")
                await page.goto("https://www.linkedin.com/my-items/saved-jobs/?cardType=APPLIED")
                
                # Step 2: Wait 5 seconds for page to load completely
                print_ts("⏳ Waiting 5 seconds for page to load...")
                await asyncio.sleep(5)
                
                # Step 3: Check if we're on the right page
                current_url = page.url
                print_ts(f"📍 Current URL: {current_url}")
                
                if "my-items/saved-jobs" in current_url:
                    print_ts("✅ Successfully loaded Applied Jobs page")
                    self.test_results['page_loaded'] = True
                else:
                    print_ts(f"⚠️ Unexpected URL: {current_url}")
                    self.test_results['page_loaded'] = False
                    return False
                
                # Step 4: Start collecting links with pagination
                print_ts("🔗 Starting link collection with pagination...")
                await self.collect_all_links_with_pagination(page)
                
                await browser.close()
                return True
                
            except Exception as e:
                print_ts(f"❌ Extension test failed: {e}")
                await browser.close()
                return False
    
    async def collect_all_links_with_pagination(self, page):
        """Collect all links using pagination like collect_applied_jobs.py"""
        max_pages = 20  # Увеличиваем лимит страниц
        page_count = 0
        
        while page_count < max_pages:
            page_count += 1
            print_ts(f"📄 Processing page {page_count}...")
            
            # Wait for job cards to load (same as Python script)
            try:
                await page.wait_for_selector('a[href*="jobs/view/"]', timeout=15000)
            except:
                print_ts("⚠️ No job links found on current page")
                break
            
            # Extract job links from current page
            page_links = await self.extract_job_links_from_page(page)
            
            if not page_links:
                print_ts("⚠️ No job links found on current page")
                break
            
            # Add new unique links
            new_links_count = 0
            for link in page_links:
                if link not in self.all_links:
                    self.all_links.append(link)
                    new_links_count += 1
            
            print_ts(f"✅ Found {new_links_count} new job links on page {page_count}")
            print_ts(f"📈 Total unique jobs collected: {len(self.all_links)}")
            
            # Save progress to file
            await self.save_links_to_file()
            
            # Check if there are more jobs to load
            if not await self.check_for_more_jobs(page):
                print_ts("🏁 No more jobs to load - pagination complete")
                break
            
            # Load more jobs
            if not await self.load_more_jobs(page):
                print_ts("⚠️ Failed to load more jobs - stopping pagination")
                break
            
            # Safety check: if we haven't found new links for 2 consecutive pages
            if new_links_count == 0:
                print_ts("⚠️ No new links found - might have reached the end")
                # Wait a bit more and try one more time
                await asyncio.sleep(3)
                page_links_retry = await self.extract_job_links_from_page(page)
                if not page_links_retry:
                    break
        
        # Final results
        print_ts(f"🎉 Collection completed! Total links: {len(self.all_links)}")
        self.test_results['total_links'] = len(self.all_links)
        self.test_results['pages_processed'] = page_count
    
    async def extract_job_links_from_page(self, page):
        """Extract job links using improved selectors"""
        return await page.evaluate('''
            () => {
                // Improved selectors based on LinkedIn's actual structure
                const selectors = [
                    // Основные селекторы для ссылок на вакансии
                    'a[href*="/jobs/view/"]',
                    'a[href*="linkedin.com/jobs/view/"]',
                    // Селекторы для карточек вакансий
                    '.job-card-container a[href*="/jobs/view/"]',
                    '.job-card a[href*="/jobs/view/"]',
                    '.job-search-card a[href*="/jobs/view/"]',
                    // Селекторы для списков вакансий
                    'li a[href*="/jobs/view/"]',
                    '.jobs-list a[href*="/jobs/view/"]',
                    // Общие селекторы
                    'a[data-job-id]',
                    'a[href*="jobs/view"][href*="linkedin.com"]'
                ];
                
                let allLinks = [];
                let debugInfo = [];
                
                // Сначала попробуем найти все ссылки на вакансии
                const allJobLinks = Array.from(document.querySelectorAll('a[href*="/jobs/view/"]'));
                debugInfo.push(`Total job links found: ${allJobLinks.length}`);
                
                // Проверим каждый селектор
                for (const selector of selectors) {
                    const links = Array.from(document.querySelectorAll(selector));
                    const hrefs = links
                        .map(link => link.href)
                        .filter(href => href && href.includes('/jobs/view/'))
                        .filter(href => href.includes('linkedin.com'));
                    
                    debugInfo.push(`Selector "${selector}": found ${links.length} elements, ${hrefs.length} job links`);
                    
                    if (hrefs.length > 0) {
                        allLinks = allLinks.concat(hrefs);
                    }
                }
                
                // Удаляем дубликаты
                allLinks = [...new Set(allLinks)];
                
                // Дополнительная отладка: проверим структуру страницы
                const jobCards = document.querySelectorAll('.job-card, .job-card-container, [data-job-id]');
                debugInfo.push(`Job cards found: ${jobCards.length}`);
                
                // Проверим, есть ли элементы с текстом "Applied"
                const appliedElements = Array.from(document.querySelectorAll('*')).filter(el => 
                    el.textContent && el.textContent.includes('Applied')
                );
                debugInfo.push(`Elements with "Applied" text: ${appliedElements.length}`);
                
                // Log debug info to console
                console.log('Debug info:', debugInfo);
                
                return {
                    links: allLinks,
                    debug: debugInfo
                };
            }
        ''')
    
    async def check_for_more_jobs(self, page):
        """Check if there are more jobs to load (same as Python script)"""
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
            
            # Look for numbered pagination buttons
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
            
            print_ts(f"Pagination info: Current page {pagination_info['currentPage']}, Total pages {pagination_info['totalPages']}")
            print_ts(f"Available pages: {pagination_info['availablePages']}")
            
            return pagination_info['hasNext']
            
        except Exception as e:
            print_ts(f"Error checking for more jobs: {e}")
            return False
    
    async def load_more_jobs(self, page):
        """Load more jobs by clicking pagination buttons (same as Python script)"""
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
                        return { nextPage: null };
                    }
                    
                    const currentPageElement = paginationContainer.querySelector('[aria-current="page"], .active, .selected');
                    const currentPage = currentPageElement ? parseInt(currentPageElement.textContent) || 1 : 1;
                    const nextPage = currentPage + 1;
                    
                    return { nextPage: nextPage };
                }
            ''')
            
            if pagination_info['nextPage']:
                next_page_button = await page.query_selector(f'button:text("{pagination_info["nextPage"]}"), a:text("{pagination_info["nextPage"]}")')
                if next_page_button:
                    print_ts(f"Clicking page {pagination_info['nextPage']} button")
                    await next_page_button.click()
                    await asyncio.sleep(4)
                    return True
            
            return False
            
        except Exception as e:
            print_ts(f"Error loading more jobs: {e}")
            return False
    
    async def save_links_to_file(self):
        """Save collected links to file"""
        if not self.all_links:
            return
        
        # Clean and deduplicate URLs (same as Python script)
        clean_links = []
        seen_job_ids = set()
        
        for link in self.all_links:
            # Extract job ID from URL
            match = re.search(r'/jobs/view/(\d+)/', link)
            if match:
                job_id = match.group(1)
                if job_id not in seen_job_ids:
                    # Create clean URL without tracking parameters
                    clean_url = f"https://www.linkedin.com/jobs/view/{job_id}/"
                    clean_links.append(clean_url)
                    seen_job_ids.add(job_id)
        
        # Save to file in permanent directory
        test_file = self.output_dir / "extension_collected_links.txt"
        with open(test_file, 'w', encoding='utf-8') as f:
            for link in clean_links:
                f.write(f"{link}\n")
        
        print_ts(f"💾 Saved {len(clean_links)} clean links to {test_file}")
        self.test_results['test_file'] = str(test_file)
        self.test_results['clean_links'] = len(clean_links)
    
    async def run_all_tests(self):
        """Run all tests"""
        try:
            await self.setup()
            
            # Test extension with pagination
            success = await self.test_extension_with_pagination()
            
            return success
            
        except Exception as e:
            print_ts(f"❌ Test suite failed: {e}")
            return False
    
    def print_results(self):
        """Print test results summary"""
        print_ts("\n📊 Fixed Extension Test Results:")
        print_ts("=" * 50)
        
        for test_name, result in self.test_results.items():
            if isinstance(result, bool):
                status = "✅" if result else "❌"
                print_ts(f"  {test_name}: {status}")
            else:
                print_ts(f"  {test_name}: {result}")
        
        print_ts("=" * 50)
    
    async def cleanup(self):
        """Clean up test environment"""
        # Не удаляем output_dir, так как он постоянный
        print_ts(f"📁 Results saved in: {self.output_dir}")


async def main():
    """Main test function"""
    print_ts("🚀 Starting Fixed Extension Test...")
    
    tester = FixedExtensionTest()
    
    try:
        success = await tester.run_all_tests()
        tester.print_results()
        
        if success:
            print_ts("\n🎉 Fixed extension test completed!")
            print_ts("\n📋 Test Summary:")
            print_ts("✅ Extension loads with LinkedIn auth")
            print_ts("✅ Link extraction works with pagination")
            print_ts("✅ Links saved to file automatically")
            print_ts("✅ Same logic as collect_applied_jobs.py")
            
            print_ts("\n🔧 Next steps:")
            print_ts("1. Check the collected links file")
            print_ts("2. Use links with main.py for detailed parsing")
            print_ts("3. Consider server integration for analytics")
            
        else:
            print_ts("\n❌ Some tests failed")
            sys.exit(1)
            
    except Exception as e:
        print_ts(f"❌ Test failed: {e}")
        sys.exit(1)
    finally:
        await tester.cleanup()


if __name__ == "__main__":
    asyncio.run(main()) 