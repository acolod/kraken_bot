# bot/telegram_handler.py - v0.1.0
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.helpers import escape_markdown # Import the official escaper

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
        self.application.add_handler(CommandHandler("help", self.help_command_handler)) # Add /help handler
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        logger.info("Telegram handlers set up.")

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Sends a welcome message when the /start command is issued."""
        user_name = update.effective_user.first_name
        # Construct the plain text message first
        plain_welcome_text = f"Hello {user_name}! I am your Kraken Trading Partner. How can I help you today? Type /help or ask me what I can do."
        # Then escape the entire plain text message for MarkdownV2
        final_welcome_text = escape_markdown(plain_welcome_text, version=2)
        await update.message.reply_text(final_welcome_text, parse_mode='MarkdownV2')
        logger.info(f"Sent welcome message to user {update.effective_user.id} ({user_name})")

    async def help_command_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Sends the help menu when /help command is issued."""
        user_id = str(update.effective_user.id)
        logger.info(f"Received /help command from user {user_id}")
        # Directly trigger the help intent in orchestrator by sending a specific message
        # that the LLM is already trained to interpret as 'get_help'.
        # Or, we could add a more direct method to Orchestrator if preferred.
        response = await self.orchestrator.process_user_message("show help menu", user_id)
        await update.message.reply_text(response, parse_mode='MarkdownV2')

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handles general text messages from the user."""
        user_message = update.message.text
        user_id = str(update.effective_user.id)
        logger.info(f"Received message from user {user_id}: {user_message}")
        # LLMHandler.generate_response will now return a string that is:
        # 1. The pre-formatted help menu, correctly escaped by escape_markdown(help_text, version=2)
        # 2. LLM-generated plain text, which was then escaped by escape_markdown(generated_text, version=2)
        # So, the 'response' here is always ready for parse_mode='MarkdownV2' and should not be escaped again.
        response = await self.orchestrator.process_user_message(user_message, user_id)
        await update.message.reply_text(response, parse_mode='MarkdownV2')