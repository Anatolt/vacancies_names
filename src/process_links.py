"""
Main link processing module.
"""

import os
import asyncio
import json
from datetime import datetime
from typing import List, Tuple, Dict, Any
from dotenv import load_dotenv
import pandas as pd
from playwright.async_api import async_playwright

from src.utils import (
    print_ts, is_valid_auth_state, setup_debug_dirs, save_debug_info,
    send_telegram_message, to_job_view_url, BrowserClosedError, 
    STORAGE_STATE_FILE
)
from src.linkedin_auth import linkedin_login
from src.parsers import extract_linkedin, extract_generic


def load_history(history_path: str) -> Dict[str, Dict[str, Any]]:
    """
    Load comprehensive history from JSON file.
    
    Returns:
        Dict mapping URLs to their full job data
    """
    if not os.path.exists(history_path):
        return {}
    
    history = {}
    try:
        with open(history_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                
                # Try to parse as JSON (new format)
                try:
                    data = json.loads(line)
                    if isinstance(data, dict) and 'url' in data:
                        history[data['url']] = data
                except json.JSONDecodeError:
                    # Fallback for old format (plain URLs)
                    history[line] = {'url': line, 'title': None, 'location': None, 'description': None}
        
        print_ts(f"Loaded {len(history)} entries from history")
        return history
        
    except Exception as e:
        print_ts(f"Error loading history: {e}")
        return {}


def save_history_entry(history_path: str, job_data: Dict[str, Any]) -> None:
    """
    Save a single job entry to history file in JSON format.
    
    Args:
        history_path: Path to history file
        job_data: Dictionary containing job information
    """
    try:
        # Ensure directory exists
        os.makedirs(os.path.dirname(history_path), exist_ok=True)
        
        # Add timestamp
        job_data['processed_at'] = datetime.now().isoformat()
        
        # Append to history file as JSON line
        with open(history_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(job_data, ensure_ascii=False) + '\n')
            
    except Exception as e:
        print_ts(f"Error saving to history: {e}")


async def run_scraper(urls: List[str], email: str, password: str, output_csv: str, debug: bool = False, history_path: str = "data/history.txt") -> Tuple[int, int]:
    """
    Main scraper function that processes a list of URLs.
    
    Args:
        urls: List of URLs to process
        email: LinkedIn email for authentication
        password: LinkedIn password for authentication
        output_csv: Path to output CSV file
        debug: Enable debug mode (saves HTML and screenshots)
        history_path: Path to history file for tracking processed URLs
        
    Returns:
        Tuple of (processed_count, skipped_count)
    """
    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_csv), exist_ok=True)
    
    # Clear output file
    open(output_csv, 'w', encoding='utf-8').close()

    # Load comprehensive history
    history_data = load_history(history_path)
    history_urls = set(history_data.keys())
    
    processed_count = 0
    skipped_count = 0
    
    if debug:
        setup_debug_dirs()
        print_ts(f"Debug mode enabled - will save HTML and screenshots to debug/")
    
    try:
        async with async_playwright() as pw:
            try:
                browser = await pw.chromium.launch(headless=False, slow_mo=50)
                
                # Create context with cookies if available
                if is_valid_auth_state(STORAGE_STATE_FILE):
                    context = await browser.new_context(storage_state=STORAGE_STATE_FILE)
                    print_ts(f"Создаю контекст с сохранёнными кукисами из {STORAGE_STATE_FILE}.")
                else:
                    context = await browser.new_context()
                    print_ts("Создаю новый контекст без кукисов.")
                
                page = await context.new_page()

                # Initial login check for LinkedIn URLs
                if any("linkedin.com" in u for u in urls):
                    print_ts(f"LinkedIn URLs detected in list. Ensuring login status...")
                    try:
                        await linkedin_login(page, email, password)
                    except BrowserClosedError:
                        print_ts("Browser was closed during login attempt. Aborting.")
                        return processed_count, skipped_count
                    except Exception as login_error:
                        print_ts(f"Error during login: {login_error}")
                        if debug:
                            print_ts(f"DEBUG - Full login error: {login_error}")
                
                for raw_url_input in urls:
                    # Skip if already in history
                    if raw_url_input.strip() in history_urls:
                        skipped_count += 1
                        print_ts(f"⏭️ Skipping (already processed): {raw_url_input.strip()}")
                        continue
                    
                    # Handle empty lines
                    if not raw_url_input.strip():
                        result = {"url": raw_url_input, "title": None, "location": None, "description": None}
                        pd.DataFrame([result]).to_csv(output_csv, mode='a', header=False, index=False, sep='\t')
                        print_ts(f"⚠️ Пустая строка в ссылках — добавлено пустое значение в CSV.")
                        skipped_count += 1
                        continue
                    
                    # Handle non-LinkedIn URLs
                    if "linkedin.com" not in raw_url_input:
                        result = {"url": raw_url_input, "title": None, "location": None, "description": None}
                        pd.DataFrame([result]).to_csv(output_csv, mode='a', header=False, index=False, sep='\t')
                        print_ts(f"⚠️ Не LinkedIn-ссылка: {raw_url_input} — добавлено пустое значение в CSV.")
                        skipped_count += 1
                        continue
                    
                    # Handle LinkedIn URLs without /jobs
                    if "linkedin.com" in raw_url_input and "/jobs" not in raw_url_input:
                        result = {"url": raw_url_input, "title": None, "location": None, "description": None}
                        pd.DataFrame([result]).to_csv(output_csv, mode='a', header=False, index=False, sep='\t')
                        print_ts(f"⚠️ LinkedIn-ссылка без /jobs: {raw_url_input} — добавлено пустое значение в CSV.")
                        skipped_count += 1
                        continue
                    
                    # Handle LinkedIn feed/post URLs
                    if ("linkedin.com" in raw_url_input and
                        ("/feed/" in raw_url_input or "/posts/" in raw_url_input or "/post/" in raw_url_input)):
                        result = {"url": raw_url_input, "title": None, "location": None, "description": None}
                        pd.DataFrame([result]).to_csv(output_csv, mode='a', header=False, index=False, sep='\t')
                        print_ts(f"⚠️ LinkedIn feed/post ссылка: {raw_url_input} — добавлено пустое значение в CSV.")
                        skipped_count += 1
                        continue

                    # Process valid job URL
                    url = to_job_view_url(raw_url_input.strip())
                    print_ts(f"Processing: {url}")
                    
                    try:
                        # Navigate to URL
                        await page.goto(url, timeout=10000, wait_until="domcontentloaded")
                        await page.wait_for_timeout(2000)  # Wait for dynamic content
                        
                        # Get page content
                        html_content = await page.content()
                        
                        # Save debug info if enabled
                        await save_debug_info(page, url, html_content, debug)
                        
                        # Extract job information
                        if "linkedin.com" in url:
                            title, location, description = extract_linkedin(html_content)
                        else:
                            title, location, description = extract_generic(html_content)
                        
                        # Save result
                        result = {
                            "url": url,
                            "title": title,
                            "location": location,
                            "description": description
                        }
                        
                        pd.DataFrame([result]).to_csv(output_csv, mode='a', header=False, index=False, sep='\t')
                        
                        # Save to comprehensive history
                        save_history_entry(history_path, result.copy())
                        processed_count += 1
                        
                        print_ts(f"✅ Processed: {title or 'No title'} | {location or 'No location'}")
                        
                    except BrowserClosedError:
                        print_ts("Browser was closed during processing. Aborting.")
                        break
                    except Exception as e:
                        print_ts(f"❌ Error processing {url}: {str(e)[:100]}")
                        # Save empty result for failed URLs
                        result = {"url": url, "title": None, "location": None, "description": None}
                        pd.DataFrame([result]).to_csv(output_csv, mode='a', header=False, index=False, sep='\t')
                        
                        # Save to comprehensive history even for failed URLs
                        save_history_entry(history_path, result.copy())
                        processed_count += 1

                await browser.close()
                
            except Exception as e:
                print_ts(f"Browser error: {e}")
                
    except Exception as e:
        print_ts(f"Playwright error: {e}")
    
    # History is now saved incrementally during processing
    
    return processed_count, skipped_count


def load_urls_from_file(file_path: str) -> List[str]:
    """Load URLs from a text file."""
    if not os.path.exists(file_path):
        print_ts(f"File {file_path} not found.")
        return []
    
    with open(file_path, 'r', encoding='utf-8') as f:
        urls = [line.strip() for line in f.readlines()]
    
    print_ts(f"Loaded {len(urls)} URLs from {file_path}")
    return urls


def send_completion_notification(token: str, user_id: str, processed: int, skipped: int, output_file: str) -> None:
    """Send completion notification via Telegram."""
    if not token or not user_id:
        return
        
    message = f"""
🤖 <b>Job Scraper Completed</b>

📊 <b>Results:</b>
• Processed: {processed}
• Skipped: {skipped}
• Output: {output_file}

✅ Scraping session finished successfully.
    """.strip()
    
    success = send_telegram_message(token, user_id, message)
    if success:
        print_ts("✅ Telegram notification sent")
    else:
        print_ts("❌ Failed to send Telegram notification")