# analysis/market_screener.py - v0.1.0
import logging
from kraken.client import KrakenClient, KrakenAPIError

logger = logging.getLogger(__name__)

class MarketScreener:
    """
    Screens the market for opportunities based on various criteria
    (e.g., volume, volatility, technical indicators).
    """
    def __init__(self, kraken_client: KrakenClient):
        self.kraken_client = kraken_client
        logger.info("MarketScreener initialized.")

    async def screen_for_high_volume_pairs(self, top_n: int = 5) -> dict:
        """
        Screens for pairs with the highest trading volume in the last 24 hours.
        Returns a dictionary with status and data (list of pairs or error message).
        """
        logger.info(f"Screening for top {top_n} high volume pairs...")
        action_result = {"status": "error", "data": "Failed to retrieve market data."}

        try:
            # Fetch ticker information for all pairs
            # The KrakenClient.get_ticker_information() with pair=None should fetch all.
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
                if isinstance(data, dict) and 'v' in data and isinstance(data['v'], list) and len(data['v']) >= 2:
                    try:
                        volume_24h = float(data['v'][1])
                        volume_data.append({"pair": pair, "volume_24h": volume_24h})
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Could not parse volume for pair {pair}: {data['v']}. Error: {e}")
                else:
                    logger.debug(f"Volume data missing or malformed for pair {pair}: {data}")
            
            if not volume_data:
                logger.warning("No valid volume data could be extracted from tickers.")
                action_result["data"] = "Could not extract valid volume data from the market."
                return action_result

            sorted_by_volume = sorted(volume_data, key=lambda x: x["volume_24h"], reverse=True)
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