# strategy/generator.py - v0.2.1 (Data Type Fix)
import logging
import pandas as pd
from kraken.client import KrakenClient
from analysis.technical_indicators import TechnicalIndicators

logger = logging.getLogger(__name__)

class StrategyGenerator:
    """
    Generates trading strategies (entry, stop-loss, take-profit)
    based on user goals and market analysis.
    """
    def __init__(self, kraken_client: KrakenClient, technical_indicators_analyzer: TechnicalIndicators):
        self.kraken_client = kraken_client
        self.ti_analyzer = technical_indicators_analyzer
        logger.info("StrategyGenerator initialized.")

    async def generate_breakout_strategy(self, pair: str, interval: int = 60, lookback_period: int = 24) -> dict | None:
        """
        Generates a simple breakout trading strategy based on recent highs and lows.
        """
        logger.info(f"Generating breakout strategy for {pair} on {interval}m timeframe...")

        ohlc_response = await self.kraken_client.get_ohlc_data(pair, interval=interval, since=None)

        if ohlc_response.get("error"):
            logger.error(f"Could not fetch OHLC data for {pair}: {ohlc_response['error']}")
            return None

        result_data = ohlc_response.get("result", {})
        kraken_pair_key = next((key for key in result_data if key != 'last'), None)
        if not kraken_pair_key or not result_data[kraken_pair_key]:
            logger.warning(f"No OHLC data found for {pair} in API response.")
            return None
        
        ohlc_data_list = result_data[kraken_pair_key]

        try:
            ohlc_df = pd.DataFrame(ohlc_data_list, columns=['time', 'open', 'high', 'low', 'close', 'vwap', 'volume', 'count'])
            for col in ['open', 'high', 'low', 'close']:
                ohlc_df[col] = pd.to_numeric(ohlc_df[col])
            if len(ohlc_df) < lookback_period:
                logger.warning(f"Not enough data ({len(ohlc_df)}) for lookback period of {lookback_period}.")
                return None
        except Exception as e:
            logger.error(f"Error processing OHLC data into DataFrame for {pair}: {e}")
            return None

        recent_data = ohlc_df.tail(lookback_period)
        highest_high = recent_data['high'].max()
        recent_low = recent_data['low'].min()

        if not all([pd.notna(highest_high), pd.notna(recent_low)]):
            logger.error("Could not determine valid high/low for strategy.")
            return None

        side = "buy"
        entry_price = highest_high * 1.001
        stop_loss = recent_low
        
        risk_per_unit = entry_price - stop_loss
        if risk_per_unit <= 0:
            logger.warning("Invalid risk calculation, entry is not above stop-loss.")
            return None

        take_profit = entry_price + (2 * risk_per_unit)

        reasoning = (
            f"A simple breakout strategy based on the {lookback_period}-period high. "
            f"The goal is to buy if the price breaks above the recent high of {highest_high:.2f}, "
            f"with a protective stop-loss below the recent low of {recent_low:.2f}."
        )

        # Ensure all strategy values are standard Python floats, not numpy types.
        strategy = {
            "pair": pair,
            "side": side,
            "entry": float(round(entry_price, 2)),
            "stop_loss": float(round(stop_loss, 2)),
            "take_profit": float(round(take_profit, 2)),
            "reasoning": reasoning
        }
        
        logger.info(f"Generated strategy for {pair}: {strategy}")
        return strategy