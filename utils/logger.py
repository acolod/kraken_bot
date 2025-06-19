# utils/logger.py - v0.1.0
import logging
import sys

def setup_logger(level=logging.INFO):
    """
    Configures the root logger for the application.
    """
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout)
            # You can add FileHandler here as well if you want to log to a file
            # logging.FileHandler("kraken_bot.log")
        ]
    )
    # You might want to set lower levels for specific noisy libraries if needed
    # logging.getLogger("httpx").setLevel(logging.WARNING)
    # logging.getLogger("telegram.ext").setLevel(logging.INFO)
    logging.info("Logger configured.")