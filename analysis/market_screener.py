# analysis/market_screener.py - v0.3.0 (Momentum Screener Added)
import logging
import pandas as pd
import asyncio
from kraken.client import KrakenClient, KrakenAPIError
from analysis.technical_indicators import TechnicalIndicators

logger = logging.getLogger(__name__)

class MarketScreener:
    """
    Screens the market for opportunities based on various criteria
    (e.g., volume, volatility, technical indicators).
    """
    def __init__(self, kraken_client: KrakenClient):
        self.kraken_client = kraken_client
        self.technical_analyzer = TechnicalIndicators()
        logger.info("MarketScreener initialized.")

    async def screen_for_high_volume_pairs(self, top_n: int = 20) -> dict:
        """
        Screens for pairs with the highest trading volume in the last 24 hours,
        calculated in the quote currency (e.g., USD, EUR).
        """
        logger.info(f"Screening for top {top_n} high volume pairs...")
        action_result = {"status": "error", "data": "Failed to retrieve market data."}

        try:
            tickers_response = await self.kraken_client.get_ticker_information()

            if tickers_response.get("error"):
                error_msg = tickers_response.get("error", ["Unknown error fetching all tickers."])
                logger.error(f"Error fetching all tickers: {error_msg}")
                action_result["data"] = f"Could not fetch market data: {', '.join(error_msg) if isinstance(error_msg, list) else error_msg}"
                return action_result

            all_tickers_data = tickers_response.get("result", {})
            if not all_tickers_data:
                logger.warning("No ticker data received from Kraken.")
                action_result["data"] = "No market data available to screen."
                return action_result

            volume_data = []
            for pair, data in all_tickers_data.items():
                if isinstance(data, dict) and 'v' in data and 'p' in data and isinstance(data['v'], list) and len(data['v']) >= 2 and isinstance(data['p'], list) and len(data['p']) >= 2:
                    try:
                        volume_base = float(data['v'][1])
                        vwap_24h = float(data['p'][1])
                        volume_in_quote = volume_base * vwap_24h
                        quote_currency = "USD"
                        known_quotes = ["USD", "EUR", "GBP", "JPY", "CAD", "CHF", "AUD"]
                        best_match = ""
                        for currency in known_quotes:
                            if pair.endswith(currency) and len(currency) > len(best_match):
                                best_match = currency
                        if best_match:
                            quote_currency = best_match
                        volume_data.append({
                            "pair": pair,
                            "volume_24h_quote": volume_in_quote,
                            "quote_currency": quote_currency,
                        })
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Could not parse volume/price for pair {pair}: v={data.get('v')} p={data.get('p')}. Error: {e}")
                else:
                    logger.debug(f"Volume/VWAP data missing or malformed for pair {pair}: {data}")
            
            if not volume_data:
                logger.warning("No valid volume data could be extracted from tickers.")
                action_result["data"] = "Could not extract valid volume data from the market."
                return action_result

            sorted_by_volume = sorted(volume_data, key=lambda x: x["volume_24h_quote"], reverse=True)
            top_pairs = sorted_by_volume[:top_n]
            action_result["status"] = "success"
            action_result["data"] = top_pairs
            logger.info(f"Top {len(top_pairs)} high volume pairs: {top_pairs}")

        except KrakenAPIError as e:
            logger.error(f"Kraken API error during market screening: {e.errors}")
            action_result["data"] = f"API error during market screening: {', '.join(e.errors) if isinstance(e.errors, list) else e.errors}"
        except Exception as e:
            logger.exception("Unexpected error during market screening.")
            action_result["data"] = "An unexpected internal error occurred during market screening."
        
        return action_result

    async def screen_for_momentum(self, top_n: int = 5, rsi_period: int = 14, rsi_threshold: float = 60.0, ohlc_interval: int = 1440) -> dict:
        """
        Screens for pairs with high momentum, based on RSI.
        """
        logger.info(f"Screening for top {top_n} high momentum pairs with RSI({rsi_period}) > {rsi_threshold}...")
        
        volume_result = await self.screen_for_high_volume_pairs(top_n=25)
        if volume_result["status"] != "success":
            return volume_result

        high_volume_pairs = volume_result.get("data", [])
        if not high_volume_pairs:
            return {"status": "success", "data": []}

        momentum_candidates = []
        tasks = [self._get_rsi_for_pair(pair_info["pair"], ohlc_interval, rsi_period) for pair_info in high_volume_pairs]
        results = await asyncio.gather(*tasks)

        for result in results:
            if result and result.get("rsi") and result["rsi"] >= rsi_threshold:
                momentum_candidates.append(result)

        sorted_by_rsi = sorted(momentum_candidates, key=lambda x: x["rsi"], reverse=True)
        top_momentum_pairs = sorted_by_rsi[:top_n]

        logger.info(f"Top {len(top_momentum_pairs)} momentum pairs found: {top_momentum_pairs}")
        return {"status": "success", "data": top_momentum_pairs}

    async def _get_rsi_for_pair(self, pair: str, interval: int, period: int) -> dict | None:
        """Helper function to fetch OHLC and calculate RSI for a single pair."""
        try:
            logger.debug(f"Fetching OHLC for {pair} to calculate RSI...")
            ohlc_response = await self.kraken_client.get_ohlc_data(pair=pair, interval=interval)

            if ohlc_response.get("error"):
                logger.warning(f"Could not fetch OHLC for {pair} for RSI calc: {ohlc_response['error']}")
                return None

            result_data = ohlc_response.get("result", {})
            kraken_pair_key = next((key for key in result_data if key != 'last'), None)
            
            if not kraken_pair_key or not result_data.get(kraken_pair_key):
                logger.warning(f"No OHLC data list found for {pair} in response.")
                return None

            ohlc_records = result_data[kraken_pair_key]
            ohlc_df = pd.DataFrame(ohlc_records, columns=['time', 'open', 'high', 'low', 'close', 'vwap', 'volume', 'count'])
            latest_rsi = self.technical_analyzer.calculate_rsi(ohlc_df, period=period)

            if latest_rsi is not None:
                return {"pair": pair, "rsi": round(latest_rsi, 2)}
            return None
        except Exception as e:
            logger.error(f"Failed to process RSI for pair {pair}: {e}")
            return None