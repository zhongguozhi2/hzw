from playwright.sync_api import sync_playwright
import time

def run():
    with sync_playwright() as p:
        print("Launching browser...")
        # Use system Chrome
        executable_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        try:
            browser = p.chromium.launch(headless=False, executable_path=executable_path)
        except Exception as e:
            print(f"Failed to launch system Chrome at {executable_path}: {e}")
            return
            
        context = browser.new_context()
        page = context.new_page()
        
        print("Navigating to https://www.xnowpay.com ...")
        page.goto("https://www.xnowpay.com")
        page.wait_for_load_state("networkidle")
        print(f"Page title: {page.title()}")
        
        # Check if we need to click a login button first
        login_button = page.get_by_role("link", name="Login")
        if login_button.count() > 0 and login_button.is_visible():
             print("Found 'Login' link, clicking...")
             login_button.first.click()
             page.wait_for_load_state("networkidle")
        else:
             # Try "Sign In" or "Log In"
             login_button = page.get_by_text("Log In")
             if login_button.count() > 0 and login_button.is_visible():
                  print("Found 'Log In' text, clicking...")
                  login_button.first.click()
                  page.wait_for_load_state("networkidle")
        
        print("Attempting to fill credentials...")
        try:
            # Email
            email_filled = False
            for selector in ["input[name='email']", "input[name='username']", "input[type='email']", "input[placeholder*='Email']"]:
                if page.locator(selector).count() > 0 and page.locator(selector).first.is_visible():
                    print(f"Found email field with selector: {selector}")
                    page.fill(selector, "bala@gmail.com")
                    email_filled = True
                    break
            
            if not email_filled:
                print("Could not find email field!")
            
            # Password
            password_filled = False
            for selector in ["input[name='password']", "input[type='password']", "input[placeholder*='Password']"]:
                if page.locator(selector).count() > 0 and page.locator(selector).first.is_visible():
                    print(f"Found password field with selector: {selector}")
                    page.fill(selector, "Xnowpay123456.")
                    password_filled = True
                    break
            
            if not password_filled:
                print("Could not find password field!")

            if email_filled and password_filled:
                # Click submit
                submit_button = page.locator("button[type='submit']")
                if submit_button.count() > 0:
                     print("Clicking submit button...")
                     submit_button.first.click()
                else:
                     print("Submit button not found by type, looking by text...")
                     # Try finding a button with text "Login" or "Sign In"
                     page.get_by_role("button", name="Login").click()
                
                print("Login form submitted.")
                # Wait a bit
                page.wait_for_timeout(5000)
                print(f"Current page title: {page.title()}")
                print(f"Current URL: {page.url}")
            
        except Exception as e:
            print(f"Error during interaction: {e}")

        print("\nBrowser is open. Press Enter in this terminal to close it...")
        input()
        browser.close()

if __name__ == "__main__":
    run()