import logging
import os
import subprocess
import sys
from pathlib import Path


logging.basicConfig(level=logging.INFO, format="[SETUP] %(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("setup_new_machine")

PROJECT_ROOT = Path(__file__).resolve().parent

BANNER = """
======================================================================
                  K R O N O S   I N D I A
              Auto-Setup & Configuration Wizard
======================================================================
"""


def check_python_version():
    logger.info("Checking Python version...")
    major, minor = sys.version_info.major, sys.version_info.minor
    logger.info("Detected Python %s.%s.%s", major, minor, sys.version_info.micro)
    if major < 3 or (major == 3 and minor < 8):
        logger.error("Python 3.8 or higher is required. Please upgrade.")
        sys.exit(1)
    logger.info("Python version OK.")


def ensure_working_directory():
    os.chdir(PROJECT_ROOT)
    logger.info("Working directory set to %s", PROJECT_ROOT)


def install_dependencies():
    requirements_path = PROJECT_ROOT / "requirements.txt"
    if not requirements_path.exists():
        logger.error("requirements.txt not found at %s", requirements_path)
        sys.exit(1)

    logger.info("Installing pip dependencies from %s...", requirements_path)
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(requirements_path)], check=True)
    except subprocess.CalledProcessError as e:
        logger.error("Failed to install requirements.txt: %s", e)
        sys.exit(1)

    logger.info("Installing pandas_ta compatibility package...")
    pandas_install = subprocess.run(
        [sys.executable, "-m", "pip", "install", "pandas-ta"],
        capture_output=True,
        text=True,
    )
    if pandas_install.returncode != 0:
        logger.warning("pip install pandas-ta failed, retrying from GitHub source...")
        try:
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "git+https://github.com/twopirllc/pandas-ta.git",
                ],
                check=True,
            )
        except subprocess.CalledProcessError as e:
            logger.error("Failed to install pandas_ta from GitHub: %s", e)
            sys.exit(1)

    logger.info("Dependencies installed successfully.")


def install_playwright_chromium():
    logger.info("Installing Playwright Chromium browser...")
    try:
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
        logger.info("Playwright Chromium browser installed successfully.")
    except subprocess.CalledProcessError as e:
        logger.error("Failed to install Playwright browser: %s", e)
        logger.warning("Run later with: python -m playwright install chromium")


def clone_kronos_repo():
    logger.info("Checking Kronos model repository...")
    repo_path = PROJECT_ROOT / "Kronos-repo"
    if repo_path.exists():
        logger.info("Kronos-repo already exists. Skipping clone.")
        return

    logger.info("Cloning Kronos-repo from GitHub...")
    try:
        subprocess.run(
            ["git", "clone", "https://github.com/shiyu-coder/Kronos.git", str(repo_path.name)],
            check=True,
            cwd=PROJECT_ROOT,
        )
        logger.info("Kronos-repo cloned successfully.")
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        logger.error("Failed to clone repository: %s", e)
        logger.warning("Clone manually with: git clone https://github.com/shiyu-coder/Kronos.git Kronos-repo")


def create_env_file():
    logger.info("Checking environment configuration...")
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        logger.info(".env file already exists. Skipping creation.")
        return

    logger.info("Creating a default .env file from template...")
    env_content = """# --- KRONOSINDIA ENVIRONMENT CONFIGURATION ---

# Ollama / Cloud LLM Settings
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=meta/llama-4-maverick-17b-128e-instruct
OLLAMA_TIMEOUT=120
OLLAMA_API_KEY=

# WhatsApp Alerts (Optional Twilio Integration)
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
WHATSAPP_FROM=whatsapp:+14155238886
WHATSAPP_TO=

# AWS Bedrock (Optional)
# AWS_ACCESS_KEY_ID=
# AWS_SECRET_ACCESS_KEY=
# AWS_REGION=us-east-1
# AWS_BEDROCK_MODEL=anthropic.claude-3-5-sonnet-20241022-v2:0

# Upstox API Settings (Optional)
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
        logger.error("Failed to create .env file: %s", e)
        sys.exit(1)


def main():
    print(BANNER)
    ensure_working_directory()
    check_python_version()
    install_dependencies()
    install_playwright_chromium()
    clone_kronos_repo()
    create_env_file()
    print("\n" + "=" * 70)
    print("SETUP COMPLETE")
    print("=" * 70)
    print("How to run the application:")
    print("  1. Edit .env if you need API keys.")
    print("  2. Run the main stock analysis orchestrator:")
    print("     python main.py")
    print("  3. Run the live web dashboard:")
    print("     python -m output.dashboard")
    print("======================================================================\n")


if __name__ == "__main__":
    main()
