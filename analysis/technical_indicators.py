# analysis/technical_indicators.py - v0.1.0
import logging
import pandas as pd
# import talib # if using TA-Lib
import pandas_ta as ta # if using pandas_ta

logger = logging.getLogger(__name__)

class TechnicalIndicators:
    """
    Calculates various technical indicators for given market data.
    """
    def __init__(self):
        logger.info("TechnicalIndicators initialized.")

    def calculate_rsi(self, ohlcv_df: pd.DataFrame, period: int = 14) -> pd.Series | None:
        """Calculates the Relative Strength Index (RSI)."""
        logger.debug(f"Calculating RSI with period {period}...")
        if 'close' not in ohlcv_df.columns or ohlcv_df['close'].empty:
            logger.warning("RSI calculation requires 'close' column with data.")
            return None
        try:
            # Ensure 'close' is numeric and handle potential NaNs from data source
            close_prices = pd.to_numeric(ohlcv_df['close'], errors='coerce').dropna()
            if len(close_prices) < period:
                logger.warning(f"Not enough data points ({len(close_prices)}) to calculate RSI with period {period}.")
                return None
            rsi_series = ta.rsi(close=close_prices, length=period)
            return rsi_series
        except Exception as e:
            logger.error(f"Error calculating RSI: {e}")
            return None

    def calculate_sma(self, ohlcv_df: pd.DataFrame, period: int = 20) -> pd.Series | None:
        """Calculates the Simple Moving Average (SMA)."""
        logger.debug(f"Calculating SMA with period {period}...")
        if 'close' not in ohlcv_df.columns or ohlcv_df['close'].empty:
            logger.warning("SMA calculation requires 'close' column with data.")
            return None
        try:
            close_prices = pd.to_numeric(ohlcv_df['close'], errors='coerce').dropna()
            if len(close_prices) < period:
                logger.warning(f"Not enough data points ({len(close_prices)}) to calculate SMA with period {period}.")
                return None
            sma_series = ta.sma(close=close_prices, length=period)
            return sma_series
        except Exception as e:
            logger.error(f"Error calculating SMA: {e}")
            return None