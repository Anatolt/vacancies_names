"""
LinkedIn authentication module.
"""

import os
from playwright.async_api import Page
from src.utils import (
    print_ts, check_browser_or_abort, is_valid_auth_state, 
    is_browser_alive, BrowserClosedError, LINKEDIN_LOGIN_URL, 
    LINKEDIN_PSETTINGS_URL, STORAGE_STATE_FILE, TIMEOUT
)


async def is_logged_in(page: Page) -> bool:
    """Check if user is logged in to LinkedIn."""
    print_ts(f"Checking login status by navigating to {LINKEDIN_PSETTINGS_URL}...")
    try:
        # Check browser alive before navigating
        if page.context.browser:
            await check_browser_or_abort(page.context.browser)
            
        try:
            await page.goto(LINKEDIN_PSETTINGS_URL, timeout=TIMEOUT, wait_until="networkidle")
        except Exception as e:
            print_ts(f"Error navigating to {LINKEDIN_PSETTINGS_URL} (networkidle): {str(e)[:150]}. Trying domcontentloaded...")
            
            # Check browser alive after first nav error
            if page.context.browser:
                await check_browser_or_abort(page.context.browser)
                
            try:
                await page.goto(LINKEDIN_PSETTINGS_URL, timeout=TIMEOUT, wait_until="domcontentloaded")
                await page.wait_for_timeout(3000) # Give some time for JS redirects
            except Exception as e2:
                print_ts(f"Error navigating to {LINKEDIN_PSETTINGS_URL} (domcontentloaded fallback): {str(e2)[:150]}. Assuming not logged in.")
                
                # Check browser alive after second nav error
                if page.context.browser:
                    await check_browser_or_abort(page.context.browser)
                return False

        current_url = page.url.lower()
        print_ts(f"Current URL after navigating to psettings: {current_url}")

        if "myaccount/settings" in current_url or "mypreferences/d/categories/account" in current_url:
            print_ts("✅ Login confirmed (URL indicates settings page).")
            return True
        
        # Check for common login page markers in URL
        login_url_markers = ["/login", "/uas/login", "/checkpoint/lg/login-submit"]
        if any(marker in current_url for marker in login_url_markers):
            print_ts("Login page URL detected. Not logged in.")
            return False

        # As a fallback, check for login form elements if URL is still psettings or similar non-confirmed state
        if LINKEDIN_PSETTINGS_URL.lower() in current_url or "linkedin.com/m/login" in current_url : # linkedin.com/m/login for mobile views
            login_form_selectors = ["input#username", "form.login__form", "button[type='submit'][aria-label*='Sign in']"]
            for selector in login_form_selectors:
                if await page.is_visible(selector):
                    print_ts(f"Login form element '{selector}' visible on {current_url}. Not logged in.")
                    return False
            print_ts(f"URL is {current_url}, but no definitive login form elements found. Checking for logged-in elements as a safeguard.")
            # Safeguard: if we are on psettings but don't see login form, and also don't see settings page, it's ambiguous.
            # For safety, assume not logged in unless we positively ID a settings page or a known logged-in element.
            # Example: Profile picture (though it might not be on psettings redirect before full load)
            if await page.is_visible("img.global-nav__me-photo"): # Check if profile pic is visible
                print_ts("Profile picture visible. Assuming logged in.")
                return True
            
            # Additional check for any of these common logged-in elements
            logged_in_selectors = [
                "div.feed-identity-module", # Feed identity module
                "li.global-nav__primary-item", # Nav bar items 
                "a[href^='/in/']", # Profile link
                "div[data-control-name='identity_welcome_message']" # Welcome message
            ]
            for selector in logged_in_selectors:
                if await page.is_visible(selector):
                    print_ts(f"Logged-in element '{selector}' visible. Assuming logged in.")
                    return True
        
        print_ts("Could not definitively confirm login status. Assuming not logged in for safety.")
        return False
    except BrowserClosedError:
        raise  # Re-raise to be caught by caller
    except Exception as e:
        print_ts(f"Error checking login status: {str(e)[:150]}. Assuming not logged in.")
        return False


async def linkedin_login(page: Page, email: str, password: str, force_login: bool = False) -> None:
    """Log in to LinkedIn if not already logged in."""
    print_ts("Attempting to ensure LinkedIn session is active...")
    
    # Check browser alive before trying anything
    if page.context.browser:
        await check_browser_or_abort(page.context.browser)
    
    loaded_from_storage = False
    
    # Skip auth file if force_login is True
    if not force_login and is_valid_auth_state(STORAGE_STATE_FILE):
        print_ts("Auth state файл уже был подхвачен при создании контекста браузера.")
        loaded_from_storage = True
    elif os.path.exists(STORAGE_STATE_FILE) and not is_valid_auth_state(STORAGE_STATE_FILE):
        print_ts(f"Auth file '{STORAGE_STATE_FILE}' exists but appears invalid/empty. Will perform new login.")
    else:
        print_ts(f"Auth file '{STORAGE_STATE_FILE}' not found. Will perform new login.")

    # Check browser alive after loading storage
    if page.context.browser:
        await check_browser_or_abort(page.context.browser)

    if loaded_from_storage:
        try:
            if await is_logged_in(page):
                print_ts("✅ Session active (verified after loading from storage).")
                return
            else:
                print_ts("⚠️ Auth state loaded from file, but session appears inactive. Proceeding to manual login.")
        except BrowserClosedError:
            raise
    else: # If not loaded from storage, check if we are already logged in
        try:
            if await is_logged_in(page):
                print_ts("✅ Session active (verified without loading from storage - perhaps browser was already logged in).")
                # Save this "found" state for future use
                try:
                    await page.context.storage_state(path=STORAGE_STATE_FILE)
                    print_ts(f"✅ Saved detected authentication state to {STORAGE_STATE_FILE}")
                except Exception as e:
                    print_ts(f"⚠️ Error saving detected authentication state: {e}")
                return
        except BrowserClosedError:
            raise

    # Check browser alive before form login
    if page.context.browser:
        await check_browser_or_abort(page.context.browser)

    print_ts("Performing new login via form...")
    try:
        print_ts("Открываю страницу логина с ожиданием 'domcontentloaded' (таймаут 10 сек)...")
        await page.goto(LINKEDIN_LOGIN_URL, timeout=10000, wait_until="domcontentloaded")
        
        # Check browser alive after navigation
        if page.context.browser:
            await check_browser_or_abort(page.context.browser)
            
        # Check if we're actually on the login page
        if not await page.is_visible("input#username") and not await page.is_visible("form.login__form"):
            print_ts("Login page did not load properly or we're already logged in. Checking login status...")
            if await is_logged_in(page):
                print_ts("✅ Appears we're already logged in (login form not visible)")
                # Save this state
                try:
                    await page.context.storage_state(path=STORAGE_STATE_FILE)
                    print_ts(f"✅ Saved detected authentication state to {STORAGE_STATE_FILE}")
                except Exception as e:
                    print_ts(f"⚠️ Error saving detected authentication state: {e}")
                return
            else:
                print_ts("⚠️ Not logged in, but login form not found. This is unusual.")
                return
                
        print_ts("Ожидание появления поля username...")
        await page.wait_for_selector("input#username", state="visible", timeout=10000)
        print_ts("Ожидание появления поля password...")
        await page.wait_for_selector("input#password", state="visible", timeout=10000)
        # Clear fields first
        await page.fill("input#username", "")
        await page.fill("input#password", "")
        # Fill in credentials with a small delay between fields
        print_ts("Ввожу email...")
        await page.fill("input#username", email)
        await page.wait_for_timeout(500)
        print_ts("Ввожу пароль...")
        await page.fill("input#password", password)
        print_ts("Ожидание кнопки submit...")
        await page.wait_for_selector("button[type='submit']", state="visible", timeout=10000)
        print_ts("Нажимаю submit...")
        await page.click("button[type='submit']")
        print_ts("Жду появления признака успешного входа (аватарка или меню профиля) в течение 10 секунд...")
        try:
            await page.wait_for_selector("img.global-nav__me-photo, .global-nav__me", timeout=10000)
            print_ts("Обнаружен элемент профиля — вход успешен.")
        except Exception as e:
            print_ts(f"Не удалось обнаружить элемент профиля за 10 секунд: {e}")
        current_url = page.url
        print_ts(f"Текущий URL после логина: {current_url}")
        
        # Check browser alive after form submission
        if page.context.browser:
            await check_browser_or_abort(page.context.browser)
            
        # Wait for navigation to a page that indicates login (e.g., psettings redirect or feed)
        # is_logged_in itself navigates, so we can call it directly for verification.
        print_ts("Login form submitted. Verifying login status...")
    except BrowserClosedError:
        raise
    except Exception as e:
        print_ts(f"Error during login form submission: {e}. Login may have failed.")
        # Check if browser closed during this error
        if page.context.browser:
            if not await is_browser_alive(page.context.browser):
                raise BrowserClosedError("Browser closed during login form submission")
        # Even if form submission had an error, is_logged_in might still pass if a redirect happened quickly.

    # Final verification and save state
    try:
        if await is_logged_in(page):
            print_ts("Login successful after form submission (verified). Saving authentication state...")
            try:
                await page.context.storage_state(path=STORAGE_STATE_FILE)
                print_ts(f"✅ Saved authentication state to {STORAGE_STATE_FILE}")
            except Exception as e:
                print_ts(f"❌ Error saving authentication state: {e}")
            # debug: всегда сохраняем состояние после логина
            try:
                await page.context.storage_state(path="data/linkedin_auth_debug.json")
                print_ts("[DEBUG] Сохранил состояние куки в data/linkedin_auth_debug.json после логина.")
            except Exception as e:
                print_ts(f"[DEBUG] Не удалось сохранить debug-куки: {e}")
        else:
            print_ts(f"❌ Login verification failed after form submission. Auth state NOT saved.")
            # debug: сохраняем состояние даже при неудаче
            try:
                await page.context.storage_state(path="data/linkedin_auth_debug.json")
                print_ts("[DEBUG] Сохранил состояние куки в data/linkedin_auth_debug.json после НЕУДАЧНОГО логина.")
            except Exception as e:
                print_ts(f"[DEBUG] Не удалось сохранить debug-куки: {e}")
    except BrowserClosedError:
        raise