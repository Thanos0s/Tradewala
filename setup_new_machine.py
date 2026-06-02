import os
import sys
import subprocess
import logging
import urllib.request
import json
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, format="[SETUP] %(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("setup_new_machine")

BANNER = """
======================================================================
                  K R O N O S   I N D I A
              Auto-Setup & Configuration Wizard
======================================================================
"""

def check_python_version():
    logger.info("Checking Python version...")
    major, minor = sys.version_info.major, sys.version_info.minor
    logger.info(f"Detected Python {major}.{minor}.{sys.version_info.micro}")
    if major < 3 or (major == 3 and minor < 8):
        logger.error("Python 3.8 or higher is required. Please upgrade.")
        sys.exit(1)
    logger.info("Python version OK.")

def install_dependencies():
    logger.info("Installing pip requirements.txt dependencies...")
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], check=True)
        # Install pandas_ta separately without downloading dependencies to prevent issues
        logger.info("Installing pandas-ta...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pandas-ta"], check=True)
        logger.info("Dependencies installed successfully.")
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to install python dependencies: {e}")
        sys.exit(1)

def install_playwright_chromium():
    logger.info("Installing Playwright Chromium browser...")
    try:
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
        logger.info("Playwright Chromium browser installed successfully.")
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to install Playwright browser: {e}")
        logger.warning("Make sure to install it later with: python -m playwright install chromium")

def clone_kronos_repo():
    logger.info("Checking shiyu-coder/Kronos repository...")
    repo_path = Path(__file__).resolve().parent / "Kronos-repo"
    if repo_path.exists():
        logger.info("Kronos-repo already exists. Skipping clone.")
        return
    
    logger.info("Cloning Kronos-repo from GitHub...")
    try:
        subprocess.run(["git", "clone", "https://github.com/shiyu-coder/Kronos.git", "Kronos-repo"], check=True)
        logger.info("Kronos-repo cloned successfully.")
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        logger.error(f"Failed to clone repository: {e}")
        logger.warning("Please clone the repository manually inside this folder:")
        logger.warning("git clone https://github.com/shiyu-coder/Kronos.git Kronos-repo")

# Local Ollama checks removed (using Cloud API)

def create_env_file():
    logger.info("Checking environment configuration...")
    env_path = Path(__file__).resolve().parent / ".env"
    if env_path.exists():
        logger.info(".env file already exists. Skipping creation.")
        return

    logger.info("Creating a default .env file from template...")
    env_content = """# --- KRONOSINDIA ENVIRONMENT CONFIGURATION ---

# Ollama / Cloud LLM Settings (100% Local or Cloud AI News Sentiment Analysis)
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=meta/llama-4-maverick-17b-128e-instruct
OLLAMA_TIMEOUT=120
OLLAMA_API_KEY=

# WhatsApp Alerts (Optional Twilio Integration)
# To enable real WhatsApp notifications, fill in these values:
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
WHATSAPP_FROM=whatsapp:+14155238886
WHATSAPP_TO=

# AWS Bedrock (Disabled by default, runs 100% locally)
# AWS_ACCESS_KEY_ID=
# AWS_SECRET_ACCESS_KEY=
# AWS_REGION=us-east-1
# AWS_BEDROCK_MODEL=anthropic.claude-3-5-sonnet-20241022-v2:0

# Upstox API Settings (Required for PCR & Option Chain data)
UPSTOX_API_KEY=
UPSTOX_API_SECRET=
UPSTOX_REDIRECT_URI=http://localhost:8000/
UPSTOX_ACCESS_TOKEN=
"""
    try:
        with open(env_path, "w", encoding="utf-8") as f:
            f.write(env_content)
        logger.info(".env file created successfully.")
    except Exception as e:
        logger.error(f"Failed to create .env file: {e}")

def main():
    print(BANNER)
    check_python_version()
    install_dependencies()
    install_playwright_chromium()
    clone_kronos_repo()
    create_env_file()
    print("\n" + "="*70)
    print("🎉 KRONOSINDIA SETUP COMPLETE! 🎉")
    print("="*70)
    print("How to run the application:")
    print("  1. Make sure your Nvidia API credentials are set in the .env file.")
    print("  2. Run the main stock analysis orchestrator:")
    print("     python main.py")
    print("  3. Run the live web dashboard:")
    print("     python -m output.dashboard")
    print("======================================================================\n")

if __name__ == "__main__":
    main()
