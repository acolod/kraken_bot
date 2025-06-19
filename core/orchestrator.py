# core/orchestrator.py - v0.1.0
import logging
from .llm_handler import LLMHandler
from kraken.client import KrakenClient
from analysis.market_screener import MarketScreener
from analysis.technical_indicators import TechnicalIndicators
from strategy.generator import StrategyGenerator
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

        # Thought: Interpret user request
        interpretation = await self.llm_handler.interpret_user_request(user_message)
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

        if intent == "get_balance":
            logger.info("Orchestrator: Intent is get_balance.")
            balance_data = await self.kraken_client.get_account_balance()
            # KrakenClient.get_account_balance() now returns a dict like {'error': [], 'result': {...balances...}}
            if not balance_data.get("error"):
                action_result["status"] = "success"
                action_result["data"] = balance_data.get("result", {}) # Pass only the result part
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
                        # Assuming the first key in result_dict is the correct pair data
                        # Kraken API often returns result like: {'XXBTZUSD': {'a': ..., 'c': [price, vol], ...}}
                        # We need to find the actual pair key returned by Kraken, it might not be what user typed.
                        actual_kraken_pair_key = next(iter(result_dict.keys()), None)
                        if actual_kraken_pair_key and actual_kraken_pair_key in result_dict:
                            price_info_array = result_dict[actual_kraken_pair_key].get('c', [None, None])
                            price = price_info_array[0] if price_info_array and price_info_array[0] is not None else None
                            if price:
                                action_result["status"] = "success"
                                action_result["data"] = {"pair": pair, "last_trade_price": price} # Use user's pair for display
                            else:
                                action_result["data"] = f"Price information not found for {pair} in API response."
                        else:
                             action_result["data"] = f"Could not find data for {pair} (or its Kraken equivalent) in API response."
                    else:
                        action_result["data"] = f"Could not find data for {pair} in API response."
                else:
                    error_msg = ticker_data.get("error", [f"Unknown error retrieving price for {pair}."])
                    action_result["data"] = f"Failed to retrieve price for {pair}: {', '.join(error_msg) if isinstance(error_msg, list) else error_msg}"
            else:
                action_result["status"] = "error"
                action_result["data"] = "Trading pair not specified for getting price."
        elif intent == "screen_market":
            logger.info("Orchestrator: Intent is screen_market.")
            # Example: top_n = parameters.get("top_n", 5)
            market_data = await self.market_screener.screen_for_high_volume_pairs() # Add params as needed
            if isinstance(market_data, list):
                action_result["status"] = "success"
                action_result["data"] = market_data
            else:
                action_result["status"] = "error"
                action_result["data"] = "Failed to retrieve market screening data."
        # elif intent == "error_llm_call": # If you add specific error handling from LLM
        #     logger.error(f"Orchestrator: LLM call failed. Error: {interpretation.get('parameters', {}).get('error_message')}")
        #     action_result["status"] = "error"
        #     action_result["data"] = "I had trouble understanding your request due to an LLM issue."
        else:
            logger.warning(f"Orchestrator: Unknown intent '{intent}'.")
            action_result["status"] = "success" # It's a success in processing, just unknown action
            action_result["data"] = f"I received your message: '{original_msg_for_response}', but I'm not sure how to help with that yet."

        # Thought: Generate a response
        response_text = await self.llm_handler.generate_response(action_result)
        logger.info(f"Generated response: {response_text}")

        return response_text