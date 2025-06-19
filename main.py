# kraken_bot/main.py - v0.1.0
import asyncio
import sys
import logging

from bot.telegram_handler import TelegramHandler
from config.settings import TELEGRAM_BOT_TOKEN, KRAKEN_API_KEY, KRAKEN_PRIVATE_KEY, LLM_API_KEY, missing_vars as missing_critical_env_vars
from core.orchestrator import Orchestrator
from kraken.client import KrakenClient
from utils.logger import setup_logger

# Removed async def main() wrapper. Setup will be synchronous.
# The async part will be handled by application.run_polling() directly.

if __name__ == "__main__":
    setup_logger()
    logger = logging.getLogger(__name__)
    logger.info("Starting Kraken Trading Bot...")

    if missing_critical_env_vars:
        logger.error(f"Exiting due to missing critical environment variables: {', '.join(missing_critical_env_vars)}")
        sys.exit(1) # Use sys.exit for exiting from __main__ block

    kraken_client = KrakenClient(api_key=KRAKEN_API_KEY, private_key=KRAKEN_PRIVATE_KEY)
    orchestrator = Orchestrator(llm_api_key=LLM_API_KEY, kraken_client=kraken_client)
    
    telegram_handler = TelegramHandler(token=TELEGRAM_BOT_TOKEN, orchestrator=orchestrator)
    application = telegram_handler.application

    try:
        logger.info("Running Telegram application polling...")
        # asyncio.run() will manage the event loop for application.run_polling()
        # application.run_polling() is an async method that handles:
        # - application.initialize()
        # - application.updater.start_polling()
        # - application.start() (starts the dispatcher)
        # - await application.updater.idle() (keeps the bot running)
        # - application.shutdown() (on exit or interruption)
        asyncio.run(application.run_polling())
    except KeyboardInterrupt: # asyncio.run will raise this on Ctrl+C
        logger.info("Polling stopped by user (KeyboardInterrupt).")
    except Exception as e:
        logger.exception(f"An unhandled exception occurred in main: {e}")
    finally:
        logger.info("Kraken Trading Bot stopped.")