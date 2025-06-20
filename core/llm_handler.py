# core/llm_handler.py - v0.2.0
import logging
import json
import google.generativeai as genai
from google.api_core import exceptions as google_exceptions
from telegram.helpers import escape_markdown # Import the official escaper
logger = logging.getLogger(__name__)

class LLMHandler:
    """
    Handles interactions with the Large Language Model (LLM).
    This class is responsible for sending prompts to the LLM,
    parsing its responses, and extracting actionable information or
    formatted text for the user.
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
                # Model for interpretation (expects JSON output)
                self.model_interpret = genai.GenerativeModel(
                    "gemini-2.0-flash-lite",
                    generation_config=genai.types.GenerationConfig(response_mime_type="application/json")
                )
                # Model for general response generation
                self.model_generate = genai.GenerativeModel("gemini-2.0-flash-lite")
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
            logger.error("LLM client not initialized. Falling back to basic mock.")
            # Fallback to very basic mock if client failed to init
            if "balance" in user_message.lower():
                return {"intent": "get_balance", "entities": {}, "parameters": {}, "original_message": user_message}
            elif "price of" in user_message.lower():
                pair_str = user_message.lower().split("price of")[1].strip().upper()
                if '/' not in pair_str and '-' not in pair_str: # e.g. "btc"
                    pair_str = f"{pair_str}/USD"
                else: # e.g. "btc/usd" or "btc-usd"
                    pair_str = pair_str.replace('-', '/')
                return {"intent": "get_ticker_price", "entities": {"pair": pair_str}, "parameters": {}, "original_message": user_message}
            return {"intent": "unknown", "entities": {}, "parameters": {}, "original_message": user_message}

        system_prompt = """
You are an AI assistant for a cryptocurrency trading bot. Your task is to interpret user requests.
You MUST respond with a valid JSON object.

The JSON object should contain:
- "intent": One of 'get_balance', 'get_ticker_price', 'screen_market', 'get_ohlc_data', 'get_sma', 'get_help', 'clarification_needed', 'unknown'.
- "entities": A dictionary of extracted entities.
- "original_intent_for_clarification" (string, optional): If intent is 'clarification_needed', this field should contain the original intent that requires clarification (e.g., 'get_ticker_price').
- "original_entities_for_clarification" (dict, optional): If intent is 'clarification_needed', this field should contain any entities already extracted for the original intent.

- For 'get_balance', entities should be empty.
- For 'get_ticker_price':
    - entities should include a 'pair' (e.g., "BTC/USD").
    - If the user only mentions a single currency (e.g., "price of btc"), assume the pair is against USD (e.g., "BTC/USD").
    - Normalize the pair to use '/' as a separator (e.g., "BTC-USD" becomes "BTC/USD").
    - If 'pair' is missing (e.g., "what's the price?"), set intent to 'clarification_needed', original_intent_for_clarification to 'get_ticker_price', and entities to {"question": "Which trading pair are you interested in for the price?"}.
- For 'get_ohlc_data':
    - entities should include a 'pair' (e.g., "ETH/USD").
    - entities might include an 'interval' (e.g., "1h", "4h", "1d", "1w", "15m"). Default to "1h" if not specified.
    - If 'pair' is missing (e.g., "show me candles"), set intent to 'clarification_needed', original_intent_for_clarification to 'get_ohlc_data', and entities to {"question": "Which trading pair do you want OHLC data for?"}.
    - If 'pair' is present but 'interval' seems ambiguous or missing for a specific request for OHLC, set intent to 'clarification_needed', original_intent_for_clarification to 'get_ohlc_data', original_entities_for_clarification to {"pair": "extracted_pair"}, and entities to {"question": "What interval would you like for the OHLC data (e.g., 1h, 4h, 1d)?"}.
- For 'get_sma':
    - entities should include 'pair' (e.g., "BTC/USD").
    - entities should include 'interval' (e.g., "1h", "4h"). Default to "1h" if not specified.
    - entities should include 'period' (e.g., 20, 50). Default to 20 if not specified.
    - If 'pair' is missing, ask for clarification.
- For 'get_help': entities should be empty. Triggered by "help", "what can you do", "features", "how do I use this bot", "/help".
- For 'screen_market', entities might include criteria like 'high volume' or 'top gainers'. For now, just extract the intent.
- If the intent is unclear or not one of the above, set intent to 'unknown' and entities to empty.
- If a known intent is identified but crucial information is missing, and you can formulate a specific question to get that information, use the 'clarification_needed' intent. The 'entities' should then contain a 'question' field with the question for the user.

CONTEXTUAL PROCESSING:
If a 'context' is provided with the user message, it means the bot previously asked a question for clarification.
The 'context' will contain "original_intent" and "original_entities".
Use the new 'user_message' to try and fulfill the 'original_intent' by filling in the missing information from 'original_entities'.
If the new 'user_message' successfully provides the missing information, return the 'original_intent' and the now complete 'entities'.
If the new 'user_message' is still insufficient or irrelevant to the context, you can either ask another clarifying question (intent: 'clarification_needed') or set intent to 'unknown'.

Example for "what's the price of eth?":
{"intent": "get_ticker_price", "entities": {"pair": "ETH/USD"}}

Example for "my balance":
{"intent": "get_balance", "entities": {}}

Example for "what's the price?":
{"intent": "clarification_needed", "entities": {"question": "Which trading pair are you interested in for the price?"}, "original_intent_for_clarification": "get_ticker_price", "original_entities_for_clarification": {}}

Example for "show ohlc":
{"intent": "clarification_needed", "entities": {"question": "For which trading pair would you like OHLC data?"}, "original_intent_for_clarification": "get_ohlc_data", "original_entities_for_clarification": {}}

Example for "what's the 20 period sma for btc/usd on 1h?":
{"intent": "get_sma", "entities": {"pair": "BTC/USD", "interval": "1h", "period": 20}}

Example for "help":
{"intent": "get_help", "entities": {}}
"""
        try:
            # Constructing the prompt for Gemini. It's often simpler with a single prompt.
            context_str = f"\n\nPREVIOUS CONTEXT (bot asked for clarification):\n{json.dumps(context)}\n" if context else ""
            full_prompt = f"{system_prompt}{context_str}\n\nUser request: \"{user_message}\"\n\nJSON Response:"

            response = await self.model_interpret.generate_content_async(full_prompt)
            
            content = response.text # Gemini response text
            if not content:
                raise ValueError("LLM returned empty content.")
                
            logger.debug(f"LLM raw interpretation: {content}")
            parsed_response = json.loads(content)
            # Basic validation of the parsed response
            if not isinstance(parsed_response, dict) or "intent" not in parsed_response:
                raise ValueError("LLM response is not a valid JSON or missing 'intent'.")
            
            # Ensure entities is a dict, default to empty if not present or not a dict
            entities = parsed_response.get("entities", {})
            if not isinstance(entities, dict):
                logger.warning(f"LLM returned 'entities' not as a dict: {entities}. Defaulting to empty.")
                entities = {}
            
            # Ensure parameters is a dict, default to empty if not present or not a dict
            parameters = parsed_response.get("parameters", {})
            if not isinstance(parameters, dict):
                logger.warning(f"LLM returned 'parameters' not as a dict: {parameters}. Defaulting to empty.")
                parameters = {}

            # Normalize pair in entities if intent is get_ticker_price or get_ohlc_data
            intent = parsed_response.get("intent") # Re-fetch intent after potential modifications by LLM
            if intent in ["get_ticker_price", "get_ohlc_data"] and "pair" in entities:
                pair_value = str(entities["pair"]).upper()
                if '/' not in pair_value and '-' not in pair_value and len(pair_value) <= 4: # Heuristic for single asset
                     entities["pair"] = f"{pair_value}/USD"
                else:
                     entities["pair"] = pair_value.replace('-', '/')


            # Normalize pair for get_sma as well
            if intent == "get_sma" and "pair" in entities:
                pair_value = str(entities["pair"]).upper()
                if '/' not in pair_value and '-' not in pair_value and len(pair_value) <= 4:
                    entities["pair"] = f"{pair_value}/USD"
                else:
                    entities["pair"] = pair_value.replace('-', '/')
            final_interpretation = {
                "intent": intent,
                "entities": entities,
                "parameters": parameters, # Include parameters, even if empty
                "original_message": user_message
            }
            if "original_intent_for_clarification" in parsed_response:
                final_interpretation["original_intent_for_clarification"] = parsed_response["original_intent_for_clarification"]
            if "original_entities_for_clarification" in parsed_response:
                final_interpretation["original_entities_for_clarification"] = parsed_response["original_entities_for_clarification"]
            return final_interpretation

        except (google_exceptions.GoogleAPIError, google_exceptions.RetryError) as e:
            logger.error(f"Google Gemini API error during interpretation: {e}")
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM JSON response for interpretation: {e}. Response was: {content}")
        except ValueError as e: # Catch our custom ValueErrors or others
            logger.error(f"Error processing LLM response for interpretation: {e}")
        except Exception as e:
            logger.exception("Unexpected error during LLM interpretation.")
        
        # Fallback in case of any error
        return {"intent": "unknown", "entities": {}, "parameters": {}, "original_message": user_message, "error": "LLM interpretation failed"}

    async def generate_response(self, action_result: dict, context: str = "") -> str:
        """Generates a natural language response based on provided data and context."""
        logger.info(f"Generating response for data: {action_result} with context: '{context}'")

        intent = action_result.get("intent", "unknown")
        status = action_result.get("status", "error")
        action_data = action_result.get("data", {}) 
        entities = action_result.get("entities", {})
        # original_message = action_result.get("original_message", "") # LLM might not need this directly if action_result is comprehensive

        if not self.model_generate:
            logger.error("LLM (model_generate) not initialized. Using basic formatting for response.")
            # Fallback to basic formatting
            if intent == "get_help" and status == "success": # Handle help even if LLM is down
                help_content = action_result.get("data", "Could not retrieve help information.")
                # Even static help text needs escaping for special MarkdownV2 characters
                return escape_markdown(str(help_content), version=2)

            if status == "error":
                error_message = action_data if isinstance(action_data, str) else "I couldn't complete that request."
                return escape_markdown(f"Sorry, I encountered an issue: {error_message}", version=2)
            # Add more basic formatting for known intents if needed, or just a generic success
            return escape_markdown(f"Action '{intent}' completed. Data: {str(action_data)[:200]}", version=2)

        # If the intent is 'get_help' and status is 'success',
        # the data is pre-formatted markdown from the orchestrator.
        # We still need to escape it for Telegram's MarkdownV2.
        if intent == "get_help" and status == "success":
            help_content = action_result.get("data", "Could not retrieve help information.")
            return escape_markdown(str(help_content), version=2)

        # For errors, unknown intents, or new intents, use the LLM
        system_prompt = f"""
You are a helpful and concise cryptocurrency trading bot assistant.
Your task is to generate a concise and friendly response based on the provided action data.
The action data is a JSON object: {json.dumps(action_result)}

If 'status' is 'error', explain the error from 'data' in a user-friendly way.
Example: "Sorry, I encountered an issue: {action_result.get('data', 'Could not complete request')}"

If 'intent' is 'unknown', use the 'data' field (which contains a pre-formatted message) or the 'original_message' to respond.
Example: "I received your message: '{action_result.get('original_message', '')}', but I'm not sure how to help with that yet."

If 'intent' is 'get_ohlc_data' and 'status' is 'success':
  - The 'data' field will contain a dictionary with 'ohlc_records' (a list of candle data) and 'last' (timestamp of the last candle).
  - Summarize the OHLC data. For example, you could mention the number of candles retrieved, the time range (if inferable or if 'last' timestamp is useful), and perhaps the latest close price.
  - If there are many records, don't list them all. Focus on a summary or the most recent data.
  - Example for OHLC: "Fetched [number] OHLC candles for [pair] on the [interval] interval. The last candle closed at [price]."
  - You can mention the 'last' timestamp if it helps provide context about the data's recency.
  - Each record in 'ohlc_records' typically has 'time', 'open', 'high', 'low', 'close', 'vwap', 'volume', 'count'.

If 'intent' is 'screen_market' and 'status' is 'success':
  - The 'data' field will contain a list of dictionaries, each with 'pair' and 'volume_24h'.
  - Present this as a list of top N high-volume pairs.
  - Format volume numbers clearly, for example, with thousand separators and 2 decimal places (e.g., "Volume: 1,500.00").
  - Example: "Here are the top 5 high-volume pairs in the last 24 hours:\n1. BTC/USD (Volume: 1,500.00)\n2. ETH/USD (Volume: 1,200.00)..."
  - Format the volume to two decimal places.

If 'intent' is 'get_sma' and 'status' is 'success':
  - The 'data' field will contain 'pair', 'interval', 'period', and 'sma_value'.
  - Present this information clearly.
  - Example: "The [period]-period SMA for [pair] on the [interval] interval is currently [sma_value]."
  - Format the sma_value to an appropriate number of decimal places (e.g., 2 for USD pairs).
  
If 'intent' is 'clarification_needed' and 'status' is 'success':
  - The 'data' field will contain the question to ask the user.
  - Simply present this question.
  - Example: "Which trading pair are you interested in for the price?"

For other successful intents, summarize the 'data' clearly and concisely.
Generate plain text. Any necessary MarkdownV2 formatting will be applied by the calling function.
The output will be escaped by the calling function, so generate raw markdown.
Do not add conversational fluff beyond the direct answer unless the intent is 'unknown' or an error.
Be brief.
"""
        try:
            # Constructing the prompt for Gemini.
            # For response generation, the system prompt itself can be the main input.
            response = await self.model_generate.generate_content_async(system_prompt)
            generated_text = response.text

            if not generated_text:
                return escape_markdown("I'm not sure how to respond to that.", version=2)
            
            logger.debug(f"LLM raw response generation: {generated_text}")
            # LLM output is instructed to be plain text, so we escape it.
            return escape_markdown(generated_text, version=2)

        except (google_exceptions.GoogleAPIError, google_exceptions.RetryError) as e:
            logger.error(f"Google Gemini API error during response generation: {e}")
            return escape_markdown("Sorry, I had trouble formulating a response.", version=2)
        except Exception as e:
            logger.exception("Unexpected error during LLM response generation.")
            return escape_markdown("Sorry, an unexpected error occurred while I was thinking.", version=2)
