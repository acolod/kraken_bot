# analysis/technical_indicators.py - v0.2.0 (RSI enhancement)
import logging
import pandas as pd
import pandas_ta as ta

logger = logging.getLogger(__name__)

class TechnicalIndicators:
    """
    Calculates various technical indicators for given market data.
    """
    def __init__(self):
        logger.info("TechnicalIndicators initialized.")

    def calculate_rsi(self, ohlcv_df: pd.DataFrame, period: int = 14) -> float | None:
        """
        Calculates the most recent Relative Strength Index (RSI) value.
        Returns a single float value or None if calculation fails.
        """
        logger.debug(f"Calculating latest RSI with period {period}...")
        if 'close' not in ohlcv_df.columns or ohlcv_df['close'].empty:
            logger.warning("RSI calculation requires 'close' column with data.")
            return None
        try:
            close_prices = pd.to_numeric(ohlcv_df['close'], errors='coerce').dropna()
            if len(close_prices) < period:
                logger.warning(f"Not enough data points ({len(close_prices)}) to calculate RSI with period {period}.")
                return None
            
            rsi_series = ta.rsi(close=close_prices, length=period)
            if rsi_series is None or rsi_series.empty:
                logger.warning(f"RSI calculation for period {period} returned empty series.")
                return None

            latest_rsi = rsi_series.iloc[-1]
            logger.info(f"Calculated latest RSI({period}): {latest_rsi}")
            return float(latest_rsi) if pd.notna(latest_rsi) else None
        except Exception as e:
            logger.error(f"Error calculating RSI: {e}")
            return None

    def calculate_sma(self, ohlc_df: pd.DataFrame, period: int = 20) -> float | None:
        """Calculates the Simple Moving Average (SMA)."""
        logger.debug(f"Calculating SMA with period {period}...")
        if ohlc_df is None or ohlc_df.empty:
            logger.warning("SMA calculation: OHLC DataFrame is empty or None.")
            return None
        if 'close' not in ohlc_df.columns:
            logger.error("SMA calculation: 'close' column not found in OHLC DataFrame.")
            return None
        if len(ohlc_df) < period:
            logger.warning(f"SMA calculation: Not enough data points ({len(ohlc_df)}) for period {period}.")
            return None

        try:
            close_prices = pd.to_numeric(ohlc_df['close'], errors='coerce')
            if close_prices.isnull().any():
                logger.error("SMA calculation: Non-numeric values found in 'close' prices after coercion.")
                return None

            sma_series = ta.sma(close=close_prices, length=period)
            if sma_series is None or sma_series.empty:
                logger.warning(f"SMA calculation for period {period} returned empty series.")
                return None
            
            latest_sma = sma_series.iloc[-1]
            logger.info(f"Calculated SMA({period}): {latest_sma}")
            return float(latest_sma) if pd.notna(latest_sma) else None
        except Exception as e:
            logger.exception(f"Error calculating SMA({period}): {e}")
            return None