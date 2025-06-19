# bot/telegram_handler.py - v0.1.0
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from core.orchestrator import Orchestrator

logger = logging.getLogger(__name__)

class TelegramHandler:
    """Handles all interactions with the Telegram Bot API."""

    def __init__(self, token: str, orchestrator: Orchestrator):
        self.token = token
        self.orchestrator = orchestrator
        self.application = Application.builder().token(self.token).build()
        self._setup_handlers()
        logger.info("TelegramHandler initialized and handlers set up.")

    def _setup_handlers(self):
        """Sets up command and message handlers for the Telegram bot."""
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        # Add more handlers as needed (e.g., for specific commands like /balance, /trade)
        logger.info("Telegram handlers set up.")

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Sends a welcome message when the /start command is issued."""
        user_name = update.effective_user.first_name
        await update.message.reply_text(f"Hello {user_name}! I am your Kraken Trading Partner. How can I help you today?")
        logger.info(f"Sent welcome message to user {update.effective_user.id} ({user_name})")

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handles general text messages from the user."""
        user_message = update.message.text
        user_id = str(update.effective_user.id)
        logger.info(f"Received message from user {user_id}: {user_message}")
        response = await self.orchestrator.process_user_message(user_message, user_id)
        await update.message.reply_text(response)