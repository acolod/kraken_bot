# core/orchestrator.py - v0.1.0
import logging
from .llm_handler import LLMHandler
from kraken.client import KrakenClient, KrakenAPIError # Import KrakenAPIError
from analysis.market_screener import MarketScreener
from analysis.technical_indicators import TechnicalIndicators
from strategy.generator import StrategyGenerator
import pandas as pd # For SMA calculation with OHLC data
from strategy.trade_manager import TradeManager

logger = logging.getLogger(__name__)

class Orchestrator:
    """
    The central reasoning agent of the bot.
    It uses the LLM to understand user requests and then coordinates
    actions between various components (Kraken client, analysis, strategy).
    Implements the 'Thought -> Act' loop.
    """
    def __init__(self, llm_api_key: str, kraken_client: KrakenClient):
        self.llm_handler = LLMHandler(api_key=llm_api_key)
        self.kraken_client = kraken_client
        self.market_screener = MarketScreener(kraken_client=self.kraken_client)
        self.technical_analyzer = TechnicalIndicators()
        self.strategy_generator = StrategyGenerator(kraken_client=self.kraken_client, technical_indicators_analyzer=self.technical_analyzer)
        self.trade_manager = TradeManager(kraken_client=self.kraken_client)
        self.pending_clarifications = {} # Stores context for users needing clarification
        logger.info("Orchestrator initialized.")

    async def process_user_message(self, user_message: str, user_id: str) -> str:
        """
        Processes a message from the user.
        1. Interprets the message using LLM.
        2. Decides on actions based on interpretation.
        3. Calls relevant modules (Kraken, analysis, strategy).
        4. Generates a response using LLM.
        """
        logger.info(f"Processing message from user {user_id}: {user_message}")

        # Check for pending clarification for this user
        user_context = self.pending_clarifications.pop(user_id, None) # Pop to use it once
        if user_context:
            logger.info(f"Found pending clarification context for user {user_id}: {user_context}")

        # Thought: Interpret user request
        # Pass user_context if it exists
        interpretation = await self.llm_handler.interpret_user_request(user_message, context=user_context)

        logger.debug(f"LLM Interpretation: {interpretation}")

        intent = interpretation.get("intent", "unknown")
        entities = interpretation.get("entities", {})
        # parameters = interpretation.get("parameters", {}) # Not used yet, but good to have if needed
        original_msg_for_response = interpretation.get("original_message", user_message)

        # Act: Based on interpretation, call appropriate functions/tools
        action_result = {
            "status": "error",  # Default to error
            "data": "Could not understand your request.",
            "intent": intent,
            "entities": entities, # Pass entities from interpretation
            "original_message": original_msg_for_response # Pass original message
        }

        try:
            if intent == "get_balance":
                logger.info("Orchestrator: Intent is get_balance.")
                balance_data = await self.kraken_client.get_account_balance()
                if not balance_data.get("error"):
                    action_result["status"] = "success"
                    action_result["data"] = balance_data.get("result", {})
                else:
                    action_result["status"] = "error"
                    error_msg = balance_data.get("error", ["Unknown error retrieving balance."])
                    action_result["data"] = f"Failed to retrieve balance: {', '.join(error_msg) if isinstance(error_msg, list) else error_msg}"

            elif intent == "get_ticker_price":
                pair = entities.get("pair")
                if pair:
                    logger.info(f"Orchestrator: Intent is get_ticker_price for pair {pair}.")
                    ticker_data = await self.kraken_client.get_ticker_information(pair=pair)
                    if not ticker_data.get("error"):
                        result_dict = ticker_data.get("result", {})
                        if result_dict:
                            # The result_dict is now expected to be like {'PAIR_NAME': {...ticker_data...}}
                            # Find the key corresponding to the requested pair (or its Kraken equivalent)
                            # pykrakenapi often uses the requested pair string as the key, but sometimes Kraken's canonical name.
                            # Let's try the requested pair first, then iterate keys if needed.
                            price = None
                            # Try the requested pair string as the key first
                            price_info_array = result_dict.get(pair, {}).get('c', [None, None])
                            price = price_info_array[0] if price_info_array and price_info_array[0] is not None else None

                            if price is None: # If not found by requested pair, iterate keys
                                for kraken_pair_key, ticker_info in result_dict.items():
                                    # Simple check: does the Kraken key contain the base currency from the requested pair?
                                    # This is a heuristic; a better way is to use Kraken's AssetPairs endpoint.
                                    base_currency_from_pair = pair.split('/')[0] if '/' in pair else pair
                                    if base_currency_from_pair in kraken_pair_key:
                                         price_info_array = ticker_info.get('c', [None, None])
                                         price = price_info_array[0] if price_info_array and price_info_array[0] is not None else None
                                         if price:
                                             logger.debug(f"Found price using Kraken key '{kraken_pair_key}' for requested pair '{pair}'.")
                                             break # Found the price, stop searching
                            if price:
                                    action_result["status"] = "success"
                                    action_result["data"] = {"pair": pair, "last_trade_price": price}
                            else:
                                action_result["data"] = f"Price information not found for {pair} in API response."
                        else:
                            action_result["data"] = f"Could not find data for {pair} in API response."
                    else:
                        error_msg = ticker_data.get("error", [f"Unknown error retrieving price for {pair}."])
                        action_result["data"] = f"Failed to retrieve price for {pair}: {', '.join(error_msg) if isinstance(error_msg, list) else error_msg}"
                else:
                    action_result["status"] = "error"
                    action_result["data"] = "Trading pair not specified for getting price."
            
            elif intent == "get_ohlc_data":
                pair = entities.get("pair")
                interval_str = entities.get("interval", "1h") # Default to 1h if not specified by LLM

                if not pair:
                    action_result["status"] = "error"
                    action_result["data"] = "Trading pair not specified for OHLC data."
                else:
                    # Convert interval string to minutes (Kraken API standard)
                    # Valid intervals: 1, 5, 15, 30, 60, 240, 1440, 10080, 21600
                    interval_map = {
                        "1M": 1, "5M": 5, "15M": 15, "30M": 30,
                        "1H": 60, "4H": 240,
                        "1D": 1440, "1W": 10080, "15D": 21600 # Approx 15 days
                    }
                    # Normalize interval_str (e.g., "1h" -> "1H", "15m" -> "15M")
                    normalized_interval_str = interval_str.upper()
                    if not normalized_interval_str.endswith(('M', 'H', 'D', 'W')):
                        if 'M' in normalized_interval_str or 'H' in normalized_interval_str or 'D' in normalized_interval_str or 'W' in normalized_interval_str:
                            pass # Already has a unit likely
                        else: # Assume minutes if just a number, or default if unparseable
                            try:
                                if int(normalized_interval_str) in interval_map.values():
                                     normalized_interval_str = str(int(normalized_interval_str)) + "M" # temp to match map
                            except ValueError:
                                logger.warning(f"Could not parse interval '{interval_str}', defaulting to 1H.")
                                normalized_interval_str = "1H"

                    kraken_interval = interval_map.get(normalized_interval_str.upper(), interval_map.get(normalized_interval_str.replace("MIN","M").upper(), 60) ) # Default to 60 min (1H)

                    logger.info(f"Orchestrator: Intent is get_ohlc_data for pair {pair}, interval {interval_str} (Kraken: {kraken_interval} mins).")
                    ohlc_data_response = await self.kraken_client.get_ohlc_data(pair=pair, interval=kraken_interval)

                    action_result["status"] = "error" if ohlc_data_response.get("error") else "success"
                    action_result["data"] = ohlc_data_response.get("result") if not ohlc_data_response.get("error") else f"Failed to retrieve OHLC data for {pair}: {ohlc_data_response.get('error')}"
            
            elif intent == "screen_market":
                logger.info("Orchestrator: Intent is screen_market.")
                # MarketScreener now returns a dict like {'status': 'success', 'data': [...]}
                screening_result = await self.market_screener.screen_for_high_volume_pairs() # Default top_n=5
                if screening_result.get("status") == "success":
                    action_result["status"] = "success"
                    action_result["data"] = screening_result.get("data", [])
                else:
                    action_result["status"] = "error"
                    action_result["data"] = screening_result.get("data", "Failed to retrieve market screening data.")
            
            elif intent == "clarification_needed":
                question = entities.get("question", "I need a bit more information. Could you please clarify your request?")
                logger.info(f"Orchestrator: Clarification needed. Question: {question}")
                action_result["status"] = "success" # Successful interpretation leading to a question

                self.pending_clarifications[user_id] = {
                    "original_intent": interpretation.get("original_intent_for_clarification", "unknown"), # Intent that needs clarification
                    "original_entities": interpretation.get("original_entities_for_clarification", {}), # Entities gathered so far for that original_intent
                }
                action_result["data"] = question # The data for the response generator is the question itself
            
            elif intent == "get_sma":
                pair = entities.get("pair")
                interval_str = entities.get("interval", "1h") # Default to 1h
                try:
                    period = int(entities.get("period", 20)) # Default to 20
                except ValueError:
                    logger.warning(f"Invalid SMA period '{entities.get('period')}', defaulting to 20.")
                    period = 20

                if not pair:
                    action_result["status"] = "error"
                    action_result["data"] = "Trading pair not specified for SMA calculation."
                else:
                    # Convert interval string to minutes
                    interval_map = {
                        "1M": 1, "5M": 5, "15M": 15, "30M": 30, "1H": 60, "4H": 240,
                        "1D": 1440, "1W": 10080, "15D": 21600
                    }
                    normalized_interval_str = interval_str.upper()
                    # Basic normalization, can be improved
                    if not normalized_interval_str.endswith(('M', 'H', 'D', 'W')):
                         normalized_interval_str = normalized_interval_str + "H" # Default to hours if no unit

                    kraken_interval = interval_map.get(normalized_interval_str.replace("MIN","M").upper(), 60)

                    logger.info(f"Orchestrator: Intent is get_sma for {pair}, interval {interval_str} (Kraken: {kraken_interval}m), period {period}.")
                    ohlc_response = await self.kraken_client.get_ohlc_data(pair=pair, interval=kraken_interval)

                    if ohlc_response.get("error"):
                        action_result["data"] = f"Could not fetch OHLC data for {pair} to calculate SMA: {ohlc_response.get('error')}"
                    else:
                        ohlc_records = ohlc_response.get("result", {}).get("ohlc_records", [])
                        if ohlc_records:
                            ohlc_df = pd.DataFrame(ohlc_records)
                            sma_value = self.technical_analyzer.calculate_sma(ohlc_df, period=period)
                            if sma_value is not None:
                                action_result["status"] = "success"
                                action_result["data"] = {"pair": pair, "interval": interval_str, "period": period, "sma_value": sma_value}
                            else:
                                action_result["data"] = f"Could not calculate SMA for {pair} with period {period} on {interval_str} interval. Not enough data or calculation error."
                        else:
                            action_result["data"] = f"No OHLC data found for {pair} on {interval_str} interval to calculate SMA."
            
            elif intent == "get_help":
                logger.info("Orchestrator: Intent is get_help.")
                help_text = """
Hello! I'm your Kraken Trading Partner. Here's a summary of what I can do:

**Available Features:**
- **Get Account Balance**: Check your Kraken account balance.
  (e.g., "what's my balance?", "show my funds")
- **Get Ticker Price**: Get the current price of a trading pair.
  (e.g., "price of BTC/USD", "current eth price")
- **Get OHLC Data**: Fetch Open, High, Low, Close candle data for a pair and interval.
  (e.g., "show ohlc for btc/usd 1h", "candles for eth/eur 15m")
- **Calculate SMA**: Calculate the Simple Moving Average for a pair, interval, and period.
  (e.g., "20 period sma for btc/usd on 4h chart", "sma for xrp/usd interval 1d period 10")
- **Market Screener**: Find top high-volume trading pairs from the last 24 hours.
  (e.g., "screen the market", "high volume pairs", "market scan")
- **Contextual Clarification**: If your request is a bit unclear, I'll ask for more details!

**In Development (Coming Soon):**
- **General Market Summary**: Get a quick overview of current market conditions.
  (e.g., "how's the market today?", "market overview")
- **Place Trade Orders**: Place buy/sell orders (limit & market) with confirmation.
  (e.g., "buy 0.1 btc at 60000 usd")
- **More Technical Indicators**: Calculations for EMA, RSI, MACD, and more.

**Future Ideas:**
- Advanced market screening (e.g., top gainers/losers, volatility alerts)
- Portfolio performance tracking and analysis
- Basic strategy suggestions
- Crypto news summaries

Just type your request in natural language, or use `/help` anytime!
"""
                action_result["status"] = "success"
                action_result["data"] = help_text.strip() # This data will be returned as is by LLMHandler

            else: # Handles "unknown" intent from LLM or if no other intent matched
                logger.warning(f"Orchestrator: Unknown intent '{intent}'.")
                action_result["status"] = "success" 
                action_result["data"] = f"I received your message: '{original_msg_for_response}', but I'm not sure how to help with that yet."
        
        # If the intent was successfully processed (not clarification_needed and not unknown from a context)
        # and there was a context, it means the clarification was resolved.
        # The pop already removed it, so no explicit clear needed here unless we didn't pop.
        # However, if the LLM *still* needs clarification or returns unknown after context, we might re-store or handle differently.
        # For now, popping is a simple "one-shot" context.
        except KrakenAPIError as e:
            logger.error(f"Kraken API Error during intent '{intent}': {e.errors}")
            action_result["status"] = "error"
            action_result["data"] = f"Error communicating with Kraken: {', '.join(e.errors) if isinstance(e.errors, list) else e.errors}"
        except Exception as e:
            logger.exception(f"Unexpected error processing intent '{intent}' for user {user_id}")
            action_result["status"] = "error"
            action_result["data"] = "An unexpected internal error occurred."

        # Thought: Generate a response
        response_text = await self.llm_handler.generate_response(action_result)
        logger.info(f"Generated response: {response_text}")

        return response_text
