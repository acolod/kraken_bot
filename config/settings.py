# config/settings.py - v0.1.0
import os
from dotenv import load_dotenv
import logging

logger = logging.getLogger(__name__)

# Load environment variables from .env file
# Determine the project's base directory dynamically
# Assumes settings.py is in a 'config' subdirectory of the project root
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
dotenv_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)
    logger.info(f".env file loaded from {dotenv_path}")
else:
    logger.warning(f".env file not found at {dotenv_path}. Create one from .env.example or ensure environment variables are set externally.")

# Kraken API Credentials
KRAKEN_API_KEY = os.getenv("KRAKEN_API_KEY")
KRAKEN_PRIVATE_KEY = os.getenv("KRAKEN_PRIVATE_KEY")

# Telegram Bot Token
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# LLM API Key
LLM_API_KEY = os.getenv("LLM_API_KEY")

# Validate critical environment variables
CRITICAL_VARS = {
    "KRAKEN_API_KEY": KRAKEN_API_KEY,
    "KRAKEN_PRIVATE_KEY": KRAKEN_PRIVATE_KEY,
    "TELEGRAM_BOT_TOKEN": TELEGRAM_BOT_TOKEN,
    "LLM_API_KEY": LLM_API_KEY,
}

missing_vars = [name for name, value in CRITICAL_VARS.items() if not value]

if missing_vars:
    logger.error(f"Missing critical environment variables: {', '.join(missing_vars)}. Please set them in your .env file or environment.")