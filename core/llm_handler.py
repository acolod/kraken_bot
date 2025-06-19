# core/llm_handler.py - v0.1.0
import logging
import json # For the final fallback, if ever needed

logger = logging.getLogger(__name__)

class LLMHandler:
    """
    Handles interactions with the Large Language Model (LLM).
    This class will be responsible for sending prompts to the LLM,
    parsing its responses, and extracting actionable information or
    formatted text for the user.
    """
    def __init__(self, api_key: str):
        self.api_key = api_key
        # Initialize your LLM client here (e.g., OpenAI, Gemini client)
        logger.info("LLMHandler initialized.")

    async def interpret_user_request(self, user_message: str) -> dict:
        """Interprets the user's natural language request using the LLM."""
        logger.debug(f"Interpreting user request: {user_message}")
        # Placeholder: Implement LLM call to understand intent, entities, etc.
        # Example: "Find coins with high momentum and good volume"
        # LLM might return:
        # {
        #     "intent": "screen_market",
        #     "entities": {"asset_type": "coin", "base_currency": "USD"},
        #     "parameters": {"criteria": [{"type": "momentum", "value": "high"},
        #                                 {"type": "volume", "value": "good"}]},
        #     "original_message": user_message
        # }
        # --- TEMPORARY MOCKS FOR TESTING ---
        lower_message = user_message.lower()
        if "balance" in lower_message:
            logger.info("LLMHandler: Mocking 'get_balance' intent.")
            return {"intent": "get_balance", "entities": {}, "parameters": {}, "original_message": user_message}
        elif "price of" in lower_message:
            # Example: "price of BTC/USD"
            parts = lower_message.split("price of")
            if len(parts) > 1:
                pair_str = parts[1].strip().upper()
                logger.info(f"LLMHandler: Mocking 'get_ticker_price' intent for pair {pair_str}.")
                return {"intent": "get_ticker_price", "entities": {"pair": pair_str}, "parameters": {}, "original_message": user_message}
        # --- END TEMPORARY MOCKS ---
        
        return {"intent": "unknown", "entities": {}, "parameters": {}, "original_message": user_message}

    async def generate_response(self, data: dict, context: str = "") -> str:
        """Generates a natural language response based on provided data and context."""
        logger.info(f"Generating response for data: {data} with context: '{context}'")

        intent = data.get("intent", "unknown")
        status = data.get("status", "error")
        action_data = data.get("data", {}) 
        entities = data.get("entities", {})
        original_message = data.get("original_message", "")

        if status == "error":
            error_message = action_data if isinstance(action_data, str) else "I couldn't complete that request."
            return self._escape_markdown_v2(f"Sorry, I encountered an issue: {error_message}")

        if intent == "get_balance":
            if isinstance(action_data, dict) and action_data:
                # action_data is now expected to be the 'result' part of Kraken's response
                # e.g., {'ZEUR': '123.45', 'XXBT': '0.5'}
                balance_lines = ["Your account balances:"]
                for currency, amount in action_data.items():
                    try:
                        amount_float = float(amount)
                        balance_lines.append(f"- {self._escape_markdown_v2(currency)}: `{amount_float:,.2f}`")
                    except ValueError:
                        balance_lines.append(f"- {self._escape_markdown_v2(currency)}: `{self._escape_markdown_v2(str(amount))}`")
                return "\n".join(balance_lines)
            else:
                return "I couldn't retrieve your balance information at this time."
        
        elif intent == "get_ticker_price":
            pair_from_entities = entities.get("pair")
            pair_from_data = action_data.get("pair") if isinstance(action_data, dict) else None
            pair_to_display = pair_from_data or pair_from_entities or "the specified pair"
            escaped_pair = self._escape_markdown_v2(pair_to_display)

            if isinstance(action_data, dict) and action_data:
                price = action_data.get("last_trade_price")
                if price:
                    try:
                        price_float = float(price)
                        return f"The current price of {escaped_pair} is `${price_float:,.2f}`."
                    except ValueError:
                        return f"The current price of {escaped_pair} is `{self._escape_markdown_v2(str(price))}`."
                else:
                    return f"I couldn't find the price for {escaped_pair}."
            else:
                return f"I couldn't retrieve the price for {escaped_pair} at this time."

        elif intent == "unknown":
            if isinstance(action_data, str): # Orchestrator already formats a nice message for 'unknown'
                return self._escape_markdown_v2(action_data)
            else:
                escaped_orig_msg = self._escape_markdown_v2(original_message)
                return f"I'm not sure how to handle: '{escaped_orig_msg}'. Can you try rephrasing?"
        
        return self._escape_markdown_v2(f"LLM response placeholder for intent '{intent}': {str(action_data)}")

    def _escape_markdown_v2(self, text: str) -> str:
        """Escapes text for Telegram MarkdownV2 parse mode."""
        escape_chars = r'_*~`>#+-=|{}.!'
        return "".join(f'\\{char}' if char in escape_chars else char for char in str(text))