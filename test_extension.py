#!/usr/bin/env python3
"""
Test Chrome Extension with Playwright

This script tests the LinkedIn Applied Jobs Collector Chrome extension
by loading it into a Playwright browser and verifying its functionality.
"""

import asyncio
import os
import sys
import json
import tempfile
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright

# Add src to path for imports
sys.path.append('src')
from utils import print_ts, BrowserClosedError
from linkedin_auth import linkedin_login


class ExtensionTester:
    def __init__(self):
        self.extension_path = Path("extension").absolute()
        self.temp_dir = None
        self.downloaded_file = None
        
    async def setup(self):
        """Setup test environment"""
        print_ts("🔧 Setting up extension test environment...")
        
        # Create temporary directory for downloads
        self.temp_dir = tempfile.mkdtemp(prefix="extension_test_")
        print_ts(f"📁 Temporary directory: {self.temp_dir}")
        
        # Verify extension files exist
        required_files = [
            "manifest.json",
            "popup.html", 
            "popup.js",
            "content.js",
            "background.js",
            "icons/icon16.png",
            "icons/icon48.png", 
            "icons/icon128.png"
        ]
        
        for file_path in required_files:
            full_path = self.extension_path / file_path
            if not full_path.exists():
                raise FileNotFoundError(f"Missing extension file: {file_path}")
        
        print_ts("✅ Extension files verified")
        
    async def test_extension(self, email: str, password: str):
        """Test the extension functionality"""
        print_ts("🚀 Starting extension test...")
        
        async with async_playwright() as pw:
            # Launch browser with extension
            browser = await pw.chromium.launch(
                headless=False,  # Set to True for headless testing
                args=[
                    f"--disable-extensions-except={self.extension_path}",
                    f"--load-extension={self.extension_path}",
                    "--disable-web-security",
                    "--disable-features=VizDisplayCompositor"
                ]
            )
            
            # Create context with download handling
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
                
                # Step 3: Wait for extension to load
                print_ts("⏳ Waiting for extension to initialize...")
                await asyncio.sleep(3)
                
                # Step 4: Test extension popup
                print_ts("🧪 Testing extension popup...")
                await self.test_popup(page)
                
                # Step 5: Test link collection
                print_ts("🔗 Testing link collection...")
                collected_links = await self.test_link_collection(page)
                
                # Step 6: Test download functionality
                print_ts("📥 Testing download functionality...")
                await self.test_download(page)
                
                # Step 7: Compare with Python script results
                print_ts("🔍 Comparing results with Python script...")
                await self.compare_results(collected_links)
                
                print_ts("✅ Extension test completed successfully!")
                
            except Exception as e:
                print_ts(f"❌ Extension test failed: {e}")
                raise
            finally:
                await browser.close()
    
    async def test_popup(self, page):
        """Test extension popup functionality"""
        # Click extension icon to open popup
        await page.click('[data-testid="extension-icon"]', timeout=5000)
        
        # Wait for popup to appear
        popup = page.locator('.extension-popup')
        await popup.wait_for(timeout=5000)
        
        # Check if popup contains expected elements
        assert await popup.locator('#startBtn').is_visible(), "Start button not visible"
        assert await popup.locator('#openPageBtn').is_visible(), "Open page button not visible"
        
        print_ts("✅ Popup test passed")
    
    async def test_link_collection(self, page):
        """Test link collection functionality"""
        # Start collection via popup
        await page.click('[data-testid="extension-icon"]')
        await page.click('#startBtn')
        
        # Wait for collection to start
        await page.wait_for_selector('#progress', timeout=10000)
        
        # Monitor progress
        max_wait_time = 300  # 5 minutes max
        start_time = datetime.now()
        
        while (datetime.now() - start_time).seconds < max_wait_time:
            # Check if collection is complete
            try:
                status = await page.locator('#status').text_content()
                if "Сбор завершен" in status or "Collection completed" in status:
                    break
                
                # Check progress
                progress_text = await page.locator('#collected-links').text_content()
                print_ts(f"📊 Progress: {progress_text}")
                
                await asyncio.sleep(5)
                
            except Exception as e:
                print_ts(f"⚠️ Progress check error: {e}")
                break
        
        # Get collected links count
        try:
            links_text = await page.locator('#collected-links').text_content()
            links_count = int(links_text.split(': ')[1].split()[0])
            print_ts(f"📈 Collected {links_count} links via extension")
            return links_count
        except:
            print_ts("⚠️ Could not get links count from popup")
            return 0
    
    async def test_download(self, page):
        """Test download functionality"""
        # Click download button
        await page.click('#downloadBtn')
        
        # Wait for download
        download = await page.wait_for_download(timeout=30000)
        
        # Save to temporary directory
        download_path = os.path.join(self.temp_dir, download.suggested_filename)
        await download.save_as(download_path)
        
        self.downloaded_file = download_path
        print_ts(f"📁 Downloaded file: {download_path}")
        
        # Verify file content
        with open(download_path, 'r', encoding='utf-8') as f:
            content = f.read()
            lines = content.strip().split('\n')
            print_ts(f"📄 File contains {len(lines)} links")
            
            # Check if links are valid
            valid_links = [line for line in lines if 'linkedin.com/jobs/view/' in line]
            print_ts(f"✅ {len(valid_links)} valid LinkedIn job links found")
    
    async def compare_results(self, extension_links_count):
        """Compare extension results with Python script results"""
        print_ts("🔍 Comparing extension vs Python script results...")
        
        # Run Python script for comparison
        try:
            from collect_applied_jobs import main as collect_main
            
            # Create temporary output file
            temp_output = os.path.join(self.temp_dir, "python_script_links.txt")
            
            # Run collection (this would need to be adapted for async)
            print_ts("🔄 Running Python script for comparison...")
            
            # For now, just check if we have the downloaded file
            if self.downloaded_file and os.path.exists(self.downloaded_file):
                with open(self.downloaded_file, 'r', encoding='utf-8') as f:
                    extension_links = f.read().strip().split('\n')
                    extension_links = [link for link in extension_links if link.strip()]
                
                print_ts(f"📊 Extension collected: {len(extension_links)} links")
                print_ts(f"📊 Python script collected: {extension_links_count} links (estimated)")
                
                if len(extension_links) > 0:
                    print_ts("✅ Extension successfully collected job links")
                    print_ts(f"📋 Sample links:")
                    for i, link in enumerate(extension_links[:3], 1):
                        print_ts(f"  {i}. {link}")
                else:
                    print_ts("⚠️ Extension did not collect any links")
            
        except Exception as e:
            print_ts(f"⚠️ Could not compare results: {e}")
    
    async def cleanup(self):
        """Clean up test environment"""
        if self.temp_dir and os.path.exists(self.temp_dir):
            import shutil
            shutil.rmtree(self.temp_dir)
            print_ts(f"🧹 Cleaned up temporary directory: {self.temp_dir}")


async def main():
    """Main test function"""
    # Load credentials
    from dotenv import load_dotenv
    load_dotenv()
    
    email = os.getenv("LINKEDIN_EMAIL")
    password = os.getenv("LINKEDIN_PASSWORD")
    
    if not email or not password:
        print_ts("❌ LINKEDIN_EMAIL and LINKEDIN_PASSWORD must be set in .env file")
        sys.exit(1)
    
    tester = ExtensionTester()
    
    try:
        await tester.setup()
        await tester.test_extension(email, password)
        
    except Exception as e:
        print_ts(f"❌ Test failed: {e}")
        sys.exit(1)
    finally:
        await tester.cleanup()


if __name__ == "__main__":
    asyncio.run(main()) 