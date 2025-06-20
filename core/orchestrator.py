# core/orchestrator.py - v0.4.1 (Execution Error Handling)
import logging
from .llm_handler import LLMHandler
from kraken.client import KrakenClient, KrakenAPIError
from analysis.market_screener import MarketScreener
from analysis.technical_indicators import TechnicalIndicators
from strategy.generator import StrategyGenerator
import pandas as pd
from strategy.trade_manager import TradeManager

logger = logging.getLogger(__name__)

class Orchestrator:
    """
    The central reasoning agent of the bot.
    """
    def __init__(self, llm_api_key: str, kraken_client: KrakenClient):
        self.llm_handler = LLMHandler(api_key=llm_api_key)
        self.kraken_client = kraken_client
        self.market_screener = MarketScreener(kraken_client=self.kraken_client)
        self.technical_analyzer = TechnicalIndicators()
        self.strategy_generator = StrategyGenerator(kraken_client=self.kraken_client, technical_indicators_analyzer=self.technical_analyzer)
        self.trade_manager = TradeManager(kraken_client=self.kraken_client)
        self.pending_actions = {}
        logger.info("Orchestrator initialized.")

    async def process_user_message(self, user_message: str, user_id: str) -> str:
        """
        Processes a message from the user, managing conversational state.
        """
        logger.info(f"Processing message from user {user_id}: {user_message}")

        user_context = self.pending_actions.get(user_id)
        interpretation = await self.llm_handler.interpret_user_request(user_message, context=user_context)
        logger.debug(f"LLM Interpretation: {interpretation}")

        intent = interpretation.get("intent", "unknown")
        entities = interpretation.get("entities", {})
        original_msg_for_response = interpretation.get("original_message", user_message)

        action_result = {
            "status": "error", "data": "Could not understand your request.",
            "intent": intent, "entities": entities, "original_message": original_msg_for_response
        }

        try:
            if intent == "confirm_action":
                pending_action = self.pending_actions.pop(user_id, None)
                if not pending_action:
                    action_result["data"] = "I don't have a pending action for you to confirm."
                elif pending_action.get("action_type") == "execute_trade":
                    strategy_params = pending_action["strategy"]
                    logger.info(f"User confirmed trade. Executing strategy...")
                    
                    execution_result = await self.trade_manager.execute_strategy(strategy_params)
                    
                    if not execution_result.get("error"):
                        txid = execution_result.get("result", {}).get("txid", [])
                        action_result.update({"status": "success", "data": {"txid": txid}})
                    else:
                        error_list = execution_result.get("error", [])
                        error_str = "".join(map(str, error_list))
                        if "volume minimum not met" in error_str:
                            clean_error = "The trade was rejected by the exchange. The calculated trade size was below the minimum required for this pair."
                        else:
                            clean_error = f"Trade execution failed: {error_str}"
                        action_result.update({"status": "error", "data": clean_error})

            elif intent == "cancel_action":
                if user_id in self.pending_actions:
                    self.pending_actions.pop(user_id)
                    action_result.update({"status": "success", "data": "Action cancelled."})
                else:
                    action_result.update({"status": "error", "data": "There was no action to cancel."})

            elif intent in ["generate_strategy", "find_and_generate_strategy"]:
                logger.info(f"Orchestrator: Intent is {intent}.")
                strategy_data = None
                if intent == "generate_strategy":
                    pair = entities.get("pair")
                    if pair: strategy_data = await self.strategy_generator.generate_breakout_strategy(pair=pair)
                    else: action_result["data"] = "You must specify a pair to generate a strategy."
                elif intent == "find_and_generate_strategy":
                    screening_result = await self.market_screener.screen_for_momentum()
                    if screening_result.get("status") == "success" and screening_result.get("data"):
                        top_pair = screening_result["data"][0]["pair"]
                        strategy_data = await self.strategy_generator.generate_breakout_strategy(pair=top_pair)
                    else:
                        action_result["data"] = "Could not find any pairs with strong momentum to build a strategy."
                if strategy_data:
                    self.pending_actions[user_id] = {"action_type": "execute_trade", "strategy": strategy_data}
                    action_result.update({"status": "success", "data": strategy_data})
                elif "data" not in action_result or action_result["data"] == "Could not understand your request.":
                     action_result["data"] = "Could not generate a valid strategy."
            
            # --- Other existing intents ---
            elif intent == "get_help":
                logger.info("Orchestrator: Intent is get_help.")
                help_text = """
*Kraken Trading Partner Help*

I can help you with a variety of trading-related tasks. Just ask me in plain English!

*Core Features:*
- *Account Balance*: Retrieve your current Kraken account balance.
- *Ticker Price*: Obtain the real-time price of any trading pair.
- *OHLC Data*: Access historical candle data for a specific pair and timeframe.
- *Simple Moving Average (SMA)*: Calculate the SMA for a given pair and period.
- *Market Screener*: Identify high-volume or high-momentum pairs.

*Strategy & Analysis:*
- *Generate Strategy*: Create a trade plan for a specific crypto pair.
- *Find a Trade*: Let me find a high-momentum pair and generate a strategy for it.

*Under Development:*
- Trade Order Placement (with confirmation)
- Advanced Technical Indicators (EMA, RSI, MACD)
- Portfolio Performance Tracking
"""
                action_result.update({"status": "success", "data": help_text.strip()})
            
            else:
                logger.warning(f"Orchestrator: Unknown intent '{intent}'.")
                action_result.update({"status": "success", "data": "I'm not sure how to help with that yet. You can type /help to see my capabilities."})

        except Exception as e:
            logger.exception(f"Unexpected error processing intent '{intent}' for user {user_id}")
            action_result.update({"status": "error", "data": "An unexpected internal error occurred."})

        response_text = await self.llm_handler.generate_response(action_result)
        logger.info(f"Generated response: {response_text}")
        return response_text