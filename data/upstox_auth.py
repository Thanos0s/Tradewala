import os
import re
import sys
import time
import logging
import requests
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def update_env_file(access_token):
    env_path = ".env"
    if not os.path.exists(env_path):
        with open(env_path, "w") as f:
            f.write(f"UPSTOX_ACCESS_TOKEN={access_token}\n")
        return

    with open(env_path, "r") as f:
        lines = f.readlines()

    new_lines = []
    token_written = False
    for line in lines:
        if line.startswith("UPSTOX_ACCESS_TOKEN="):
            new_lines.append(f"UPSTOX_ACCESS_TOKEN={access_token}\n")
            token_written = True
        else:
            new_lines.append(line)

    if not token_written:
        # Add a newline if file doesn't end with one
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines.append("\n")
        new_lines.append(f"UPSTOX_ACCESS_TOKEN={access_token}\n")

    with open(env_path, "w") as f:
        f.writelines(new_lines)
    logging.info("Successfully updated .env with UPSTOX_ACCESS_TOKEN")

def run_login():
    load_dotenv()
    
    api_key = os.getenv("UPSTOX_API_KEY")
    api_secret = os.getenv("UPSTOX_API_SECRET")
    redirect_uri = os.getenv("UPSTOX_REDIRECT_URI", "http://localhost:8000/")

    if not api_key or not api_secret:
        logging.error("UPSTOX_API_KEY and UPSTOX_API_SECRET must be defined in your .env file!")
        sys.exit(1)

    auth_url = f"https://api.upstox.com/v2/login/authorization/dialog?response_type=code&client_id={api_key}&redirect_uri={redirect_uri}"
    
    logging.info("Starting login flow using Playwright...")
    logging.info(f"Auth URL: {auth_url}")
    
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logging.error("playwright not installed in virtual environment. Install using pip.")
        sys.exit(1)

    with sync_playwright() as p:
        # Launch Chromium or Firefox
        logging.info("Launching headful browser. Please watch for the popup browser window...")
        
        # We try to launch Chromium first, if not available, we can try Firefox or webkit
        try:
            browser = p.chromium.launch(headless=False)
        except Exception as e:
            logging.warning(f"Failed to launch Chromium ({e}), trying Firefox...")
            try:
                browser = p.firefox.launch(headless=False)
            except Exception as fe:
                logging.error(f"Failed to launch Firefox ({fe}). Please ensure playwright browser is installed.")
                sys.exit(1)

        context = browser.new_context()
        page = context.new_page()
        
        print("\n" + "="*80)
        print("ACTION REQUIRED:")
        print("1. A browser window has opened.")
        print("2. Enter your registered mobile number and PIN.")
        print("3. Enter your Microsoft Authenticator TOTP when prompted.")
        print("4. Once you log in, the browser will redirect and this script will automatically exit.")
        print("="*80 + "\n")
        
        page.goto(auth_url)
        
        # Wait for the redirect to complete
        # We poll the URL every 500ms for up to 180 seconds
        code = None
        start_time = time.time()
        timeout = 180  # 3 minutes
        
        try:
            while time.time() - start_time < timeout:
                current_url = page.url
                # Check if we are redirected to localhost with code query param
                if "code=" in current_url and redirect_uri in current_url:
                    match = re.search(r"code=([^&]+)", current_url)
                    if match:
                        code = match.group(1)
                        logging.info("Authorization code captured successfully!")
                        break
                page.wait_for_timeout(500)
        except Exception as e:
            logging.error(f"Error during browser tracking: {e}")
        
        browser.close()
        
        if not code:
            logging.error("Login timeout or browser closed before completion.")
            sys.exit(1)

        # Exchange code for access token
        logging.info("Exchanging authorization code for Access Token...")
        token_url = "https://api.upstox.com/v2/login/authorization/token"
        headers = {
            "accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        payload = {
            "code": code,
            "client_id": api_key,
            "client_secret": api_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code"
        }
        
        resp = requests.post(token_url, headers=headers, data=payload)
        if resp.status_code == 200:
            token_data = resp.json()
            access_token = token_data.get("access_token")
            if access_token:
                update_env_file(access_token)
                print("\n" + "*"*80)
                print("SUCCESS: Upstox API is now authenticated!")
                print("The access token has been saved to your .env file.")
                print("*"*80 + "\n")
            else:
                logging.error(f"Response did not contain access_token: {token_data}")
                sys.exit(1)
        else:
            logging.error(f"Failed to exchange code: {resp.status_code} - {resp.text}")
            sys.exit(1)

if __name__ == "__main__":
    run_login()
