# core/llm_handler.py - v0.4.1 (Strategy Formatting Fix)
import logging
import json
import google.generativeai as genai
from google.api_core import exceptions as google_exceptions

logger = logging.getLogger(__name__)

class LLMHandler:
    """
    Handles interactions with the Large Language Model (LLM).
    """
    def __init__(self, api_key: str):
        self.api_key = api_key
        if not self.api_key:
            logger.warning("LLM API key is not set. LLMHandler will not function.")
            self.model_interpret = None
            self.model_generate = None
        else:
            try:
                genai.configure(api_key=self.api_key)
                self.model_interpret = genai.GenerativeModel(
                    "gemini-1.5-flash-latest",
                    generation_config=genai.types.GenerationConfig(response_mime_type="application/json")
                )
                self.model_generate = genai.GenerativeModel("gemini-1.5-flash-latest")
                logger.info("LLMHandler initialized with Google Gemini models.")
            except Exception as e:
                logger.error(f"Failed to initialize Google Gemini models: {e}")
                self.model_interpret = None
                self.model_generate = None

    async def interpret_user_request(self, user_message: str, context: dict | None = None) -> dict:
        """Interprets the user's natural language request using the LLM."""
        log_context_msg = f" with context: {context}" if context else ""
        logger.debug(f"Interpreting user request with LLM: \"{user_message}\"{log_context_msg}")
        
        if not self.model_interpret:
            return {"intent": "unknown", "entities": {}, "parameters": {}, "original_message": user_message}

        system_prompt = """
You are an AI assistant for a cryptocurrency trading bot. Your task is to interpret user requests.
A 'context' object may be provided, which indicates the bot is waiting for a user's response to a question or a confirmation.
You MUST respond with a valid JSON object with an "intent" and "entities".

Intents:
'get_balance', 'get_ticker_price', 'screen_market', 'screen_for_momentum', 
'generate_strategy', 'find_and_generate_strategy', 
'confirm_action', 'cancel_action',
'get_ohlc_data', 'get_sma', 'get_help', 'clarification_needed', 'unknown'.

- If the context indicates the bot is waiting for a confirmation and the user says "yes", "confirm", "do it", "go ahead", set the intent to 'confirm_action'.
- If the user says "no", "cancel", "stop", set the intent to 'cancel_action'.
- 'find_and_generate_strategy' is a high-level command for "find me a trade".
- 'generate_strategy' is for a specific pair. It requires a 'pair' entity.
- 'screen_for_momentum' is for "high momentum pairs".
- 'screen_market' is for high volume.
"""
        try:
            context_str = f"\n\nCONTEXT (The bot is waiting for a response related to this):\n{json.dumps(context)}\n" if context else ""
            full_prompt = f"{system_prompt}{context_str}\n\nUser request: \"{user_message}\"\n\nJSON Response:"
            response = await self.model_interpret.generate_content_async(full_prompt)
            content = response.text
            logger.debug(f"LLM raw interpretation: {content}")
            return json.loads(content)
        except Exception as e:
            logger.exception(f"Unexpected error during LLM interpretation.")
            return {"intent": "unknown", "entities": {}, "parameters": {}, "original_message": user_message, "error": "LLM interpretation failed"}

    async def generate_response(self, action_result: dict, context: str = "") -> str:
        """Generates a natural language response based on provided data and context."""
        logger.info(f"Generating response for data: {action_result} with context: '{context}'")

        intent = action_result.get("intent", "unknown")
        status = action_result.get("status", "error")

        if intent == "get_help" and status == "success":
            return action_result.get("data", "An error occurred fetching the help menu.")

        if not self.model_generate:
            return json.dumps(action_result)

        system_prompt = f"""
You are an expert-level crypto trading partner. Your tone is professional, insightful, and direct.
Your task is to generate a clear, well-formatted response using basic Markdown based on the provided JSON object.

The action data JSON is:
{json.dumps(action_result)}

## Response Guidelines:
- **DO NOT** include any disclaimers or warnings.
- Use asterisks for bold (*bold*) and hyphens for lists (- list item).
- For table data, wrap the entire table in a triple-backtick code block (```) for alignment.
- For the 'generate_strategy' or 'find_and_generate_strategy' intents, present the strategy as a simple, clean list. *Do not use a table*. End with the 'reasoning' and ask the user for confirmation.
- If the intent was 'confirm_action' and status is 'success', announce that the order was placed and show the transaction ID.
- If the intent was 'cancel_action', simply confirm the action was cancelled.
- For all other intents, summarize the data clearly and professionally.
"""
        try:
            response = await self.model_generate.generate_content_async(system_prompt)
            return response.text
        except Exception as e:
            logger.exception("Unexpected error during LLM response generation.")
            return "Sorry, an unexpected error occurred while I was thinking."