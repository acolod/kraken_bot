# strategy/generator.py
import logging
from analysis.technical_indicators import TechnicalIndicators # Ensure this is uncommented
from kraken.client import KrakenClient # Ensure this is uncommented
import pandas as pd # You'll need pandas to work with OHLC data effectively

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

    async def generate_scalp_strategy(self, pair: str, interval: int = 5, risk_level: str = "low") -> dict | None:
        """
        Generates a scalp trading strategy based on recent price action and basic indicators.
        This is a very simplified example.
        :param pair: Trading pair (e.g., 'BTC/USD').
        :param interval: OHLC interval in minutes (e.g., 5 for 5-minute candles).
        :param risk_level: 'low', 'medium', 'high' - to adjust SL/TP (not fully implemented).
        :return: A dictionary with strategy parameters or None if data is insufficient.
        """
        logger.info(f"Generating scalp strategy for {pair}, interval {interval}min, risk {risk_level}...")

        # 1. Fetch recent OHLC data
        # The get_ohlc_data in your KrakenClient is set up to use pykrakenapi
        # which returns a tuple (DataFrame, dict), but your client's _make_api_call
        # was modified to return the dict part.
        # The dict response from Kraken API via pykrakenapi for OHLC data looks like:
        # {'error': [], 'result': {'PAIR_NAME': [[<timestamp>, <open>, <high>, <low>, <close>, <vwap>, <volume>, <count>], ...], 'last': <timestamp>}}
        ohlc_response = await self.kraken_client.get_ohlc_data(pair, interval=interval)

        if ohlc_response.get("error"):
            logger.error(f"Could not fetch OHLC data for {pair}: {ohlc_response['error']}")
            return None

        result_data = ohlc_response.get("result", {})
        if not result_data:
            logger.warning(f"No 'result' key in OHLC response for {pair}.")
            return None

        # The actual pair name might be different (e.g., XXBTZUSD for BTC/USD)
        # We need to get the first key in the 'result' dict that isn't 'last'
        kraken_pair_key = None
        for key_in_result in result_data.keys():
            if key_in_result != 'last':
                kraken_pair_key = key_in_result
                break
        
        if not kraken_pair_key or not result_data[kraken_pair_key]:
            logger.warning(f"No OHLC data found for {pair} (Kraken pair key: {kraken_pair_key}) in API response.")
            return None
        
        ohlc_data_list = result_data[kraken_pair_key]

        # Convert to DataFrame
        try:
            ohlcv_df = pd.DataFrame(ohlc_data_list, columns=['time', 'open', 'high', 'low', 'close', 'vwap', 'volume', 'count'])
            for col in ['open', 'high', 'low', 'close', 'volume']: # vwap and count might also be numeric
                ohlcv_df[col] = pd.to_numeric(ohlcv_df[col])
            ohlcv_df['time'] = pd.to_datetime(ohlcv_df['time'], unit='s')
            ohlcv_df.set_index('time', inplace=True)
        except Exception as e:
            logger.error(f"Error processing OHLC data into DataFrame for {pair}: {e}")
            return None

        if ohlcv_df.empty:
            logger.warning(f"OHLC DataFrame is empty for {pair} after processing.")
            return None

        # --- From here, you'd implement your strategy logic using ohlcv_df ---
        # Example:
        latest_close = ohlcv_df['close'].iloc[-1]
        # sma20 = self.ti_analyzer.calculate_sma(ohlcv_df, period=20)
        # if sma20 is None or sma20.empty:
        #     logger.warning(f"Could not calculate SMA for {pair}")
        #     return None
        # latest_sma20 = sma20.iloc[-1]

        # Dummy strategy based on latest close
        entry_price = float(latest_close)
        side = "buy" if entry_price > 50000 else "sell" # Arbitrary logic
        stop_loss = entry_price * 0.99 if side == "buy" else entry_price * 1.01
        take_profit = entry_price * 1.01 if side == "buy" else entry_price * 0.99
        
        logger.info(f"Generated scalp strategy for {pair}: Side={side}, Entry={entry_price}, SL={stop_loss}, TP={take_profit}")

        return {
            "pair": pair,
            "entry": entry_price,
            "stop_loss": round(stop_loss, 2), # Adjust precision as needed
            "take_profit": round(take_profit, 2), # Adjust precision as needed
            "side": side,
            "reason": "Dummy strategy based on latest close and SMA."
        }

    # ... other strategy methods ...
