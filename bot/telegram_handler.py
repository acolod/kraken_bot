# bot/telegram_handler.py - v0.2.0 (UX Improvement)
import logging
from telegram import Update, constants
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

logger = logging.getLogger(__name__)

class TelegramHandler:
    """Handles all interactions with the Telegram Bot API."""

    def __init__(self, token: str, orchestrator: 'Orchestrator'):
        self.token = token
        self.orchestrator = orchestrator
        self.application = Application.builder().token(self.token).build()
        self._setup_handlers()
        logger.info("TelegramHandler initialized and handlers set up.")

    def _setup_handlers(self):
        """Sets up command and message handlers for the Telegram bot."""
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command_handler))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        logger.info("Telegram handlers set up.")

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Sends a welcome message when the /start command is issued."""
        user_name = update.effective_user.first_name
        welcome_text = f"Hello {user_name}! I am your Kraken Trading Partner. How can I help you today? Type /help or ask me what I can do."
        await update.message.reply_text(welcome_text, parse_mode=constants.ParseMode.MARKDOWN)
        logger.info(f"Sent welcome message to user {update.effective_user.id} ({user_name})")

    async def help_command_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Sends the help menu when /help command is issued."""
        user_id = str(update.effective_user.id)
        logger.info(f"Received /help command from user {user_id}")
        
        # For a fast command like /help, we don't need the 'please wait' message.
        response = await self.orchestrator.process_user_message("show help menu", user_id)
        await update.message.reply_text(response, parse_mode=constants.ParseMode.MARKDOWN)

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handles general text messages from the user, including long-running ones."""
        user_message = update.message.text
        user_id = str(update.effective_user.id)
        logger.info(f"Received message from user {user_id}: {user_message}")

        # --- NEW UX LOGIC ---
        # 1. Send an immediate acknowledgment message to the user.
        # We use a thinking emoji to make it clear something is happening.
        placeholder_message = await update.message.reply_text("🤔 Thinking...")

        # 2. Process the request, which may take a long time.
        final_response = await self.orchestrator.process_user_message(user_message, user_id)

        # 3. Edit the original placeholder message with the final, formatted response.
        try:
            await placeholder_message.edit_text(
                text=final_response,
                parse_mode=constants.ParseMode.MARKDOWN
            )
        except Exception as e:
            logger.error(f"Failed to edit message, sending new one. Error: {e}")
            # As a fallback, if editing fails (e.g., response is empty), send a new message.
            await update.message.reply_text(final_response, parse_mode=constants.ParseMode.MARKDOWN)