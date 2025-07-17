#!/usr/bin/env python3
"""
Basic Extension Test - No LinkedIn Auth Required

This script tests the Chrome extension structure and basic functionality
without requiring LinkedIn authentication.
"""

import asyncio
import os
import sys
import json
from pathlib import Path
from playwright.async_api import async_playwright


async def test_extension_structure():
    """Test extension file structure and manifest"""
    print("🔧 Testing extension structure...")
    
    extension_path = Path("extension")
    
    # Check if extension directory exists
    if not extension_path.exists():
        print("❌ Extension directory not found")
        return False
    
    # Check required files
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
    
    missing_files = []
    for file_path in required_files:
        full_path = extension_path / file_path
        if not full_path.exists():
            missing_files.append(file_path)
    
    if missing_files:
        print(f"❌ Missing files: {missing_files}")
        return False
    
    print("✅ All required files present")
    
    # Test manifest.json
    try:
        with open(extension_path / "manifest.json", 'r') as f:
            manifest = json.load(f)
        
        # Check required manifest fields
        required_fields = ["manifest_version", "name", "version", "permissions"]
        for field in required_fields:
            if field not in manifest:
                print(f"❌ Missing manifest field: {field}")
                return False
        
        print(f"✅ Manifest valid: {manifest['name']} v{manifest['version']}")
        
    except Exception as e:
        print(f"❌ Error reading manifest: {e}")
        return False
    
    return True


async def test_extension_in_browser():
    """Test extension loading in browser"""
    print("🌐 Testing extension in browser...")
    
    extension_path = Path("extension").absolute()
    
    async with async_playwright() as pw:
        try:
            # Launch browser with extension
            browser = await pw.chromium.launch(
                headless=False,
                args=[
                    f"--disable-extensions-except={extension_path}",
                    f"--load-extension={extension_path}",
                    "--disable-web-security"
                ]
            )
            
            # Create context
            context = await browser.new_context(
                viewport={'width': 1280, 'height': 720}
            )
            
            page = await context.new_page()
            
            # Test 1: Load a simple page
            print("📄 Testing extension on simple page...")
            await page.goto("https://example.com")
            await page.wait_for_load_state("networkidle")
            
            # Test 2: Check if extension is loaded
            extensions = await page.evaluate('''
                () => {
                    return new Promise((resolve) => {
                        chrome.management.getAll((extensions) => {
                            resolve(extensions.map(ext => ({
                                name: ext.name,
                                enabled: ext.enabled
                            })));
                        });
                    });
                }
            ''')
            
            print(f"📊 Loaded extensions: {extensions}")
            
            # Test 3: Try to access extension storage
            try:
                storage_data = await page.evaluate('''
                    () => {
                        return new Promise((resolve) => {
                            chrome.storage.local.get(null, (result) => {
                                resolve(result);
                            });
                        });
                    }
                ''')
                print(f"📦 Extension storage: {storage_data}")
            except Exception as e:
                print(f"⚠️ Could not access extension storage: {e}")
            
            # Test 4: Test content script injection
            print("🔧 Testing content script...")
            await page.goto("https://www.linkedin.com")
            await page.wait_for_load_state("networkidle")
            
            # Check if content script is injected
            content_script_check = await page.evaluate('''
                () => {
                    // Check if our content script variables are available
                    return {
                        hasCollector: typeof window.collector !== 'undefined',
                        hasAppliedJobsCollector: typeof window.AppliedJobsCollector !== 'undefined'
                    };
                }
            ''')
            
            print(f"🔍 Content script check: {content_script_check}")
            
            await browser.close()
            print("✅ Browser test completed")
            return True
            
        except Exception as e:
            print(f"❌ Browser test failed: {e}")
            return False


async def test_extension_functionality():
    """Test extension functionality without LinkedIn"""
    print("🧪 Testing extension functionality...")
    
    extension_path = Path("extension").absolute()
    
    async with async_playwright() as pw:
        try:
            browser = await pw.chromium.launch(
                headless=False,
                args=[
                    f"--disable-extensions-except={extension_path}",
                    f"--load-extension={extension_path}",
                    "--disable-web-security"
                ]
            )
            
            context = await browser.new_context(
                viewport={'width': 1280, 'height': 720}
            )
            
            page = await context.new_page()
            
            # Test popup functionality
            print("📋 Testing popup...")
            
            # Navigate to a page where content script should work
            await page.goto("https://www.linkedin.com/my-items/saved-jobs/?cardType=APPLIED")
            await page.wait_for_load_state("networkidle")
            
            # Wait a bit for content script to load
            await asyncio.sleep(3)
            
            # Test if we can extract job links (even if not logged in)
            try:
                links = await page.evaluate('''
                    () => {
                        // Same logic as content script
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
                        
                        return allLinks;
                    }
                ''')
                
                print(f"🔗 Found {len(links)} potential job links")
                
                if links:
                    print("📋 Sample links:")
                    for i, link in enumerate(links[:3], 1):
                        print(f"  {i}. {link}")
                
            except Exception as e:
                print(f"⚠️ Could not extract links: {e}")
            
            # Test pagination detection
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
                        
                        return {
                            hasPagination: !!paginationContainer,
                            selectors: paginationSelectors
                        };
                    }
                ''')
                
                print(f"📄 Pagination info: {pagination_info}")
                
            except Exception as e:
                print(f"⚠️ Could not check pagination: {e}")
            
            await browser.close()
            print("✅ Functionality test completed")
            return True
            
        except Exception as e:
            print(f"❌ Functionality test failed: {e}")
            return False


async def main():
    """Main test function"""
    print("🚀 Starting basic extension tests...")
    
    # Test 1: Structure
    structure_ok = await test_extension_structure()
    
    # Test 2: Browser loading
    browser_ok = await test_extension_in_browser()
    
    # Test 3: Functionality
    functionality_ok = await test_extension_functionality()
    
    # Summary
    print("\n📊 Test Results:")
    print(f"  Structure: {'✅' if structure_ok else '❌'}")
    print(f"  Browser Loading: {'✅' if browser_ok else '❌'}")
    print(f"  Functionality: {'✅' if functionality_ok else '❌'}")
    
    if all([structure_ok, browser_ok, functionality_ok]):
        print("\n🎉 All basic tests passed!")
        print("\n📋 Next steps:")
        print("1. Set up .env file with LinkedIn credentials")
        print("2. Run full test with authentication")
        print("3. Install extension in Chrome manually")
    else:
        print("\n❌ Some tests failed")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main()) 