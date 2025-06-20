# kraken/client.py - v0.1.0
import logging
import krakenex # Using the krakenex library
from pykrakenapi import KrakenAPI # pykrakenapi is a wrapper around krakenex
import asyncio # For async sleep in rate limit handling
import pandas as pd # For type checking and DataFrame conversion

logger = logging.getLogger(__name__)

class KrakenAPIError(Exception):
    """Custom exception for Kraken API errors."""
    def __init__(self, message, errors=None):
        super().__init__(message)
        self.errors = errors if errors is not None else []

class KrakenClient:
    """
    Handles all API interactions with the Kraken exchange.
    This includes fetching market data, account balances,
    and executing trades.
    """
    def __init__(self, api_key: str, private_key: str, rate_limit_retry_attempts: int = 3, rate_limit_retry_delay: int = 5):
        self.api_key = api_key
        self.private_key = private_key
        self.rate_limit_retry_attempts = rate_limit_retry_attempts
        self.rate_limit_retry_delay = rate_limit_retry_delay
        
        if not api_key or not private_key:
            logger.warning("Kraken API key or private key is not set. Authenticated calls will fail.")
            self.kraken = None
            self.k = None # pykrakenapi instance
        else:
            try:
                self.kraken = krakenex.API(key=api_key, secret=private_key)
                self.k = KrakenAPI(self.kraken)
                logger.info("KrakenClient initialized with API credentials.")
            except Exception as e:
                logger.error(f"Failed to initialize KrakenAPI: {e}")
                self.kraken = None
                self.k = None
        
    async def _make_api_call(self, method_name: str, *args, **kwargs) -> dict:
        """
        Makes an API call with rate limit handling and error parsing.
        `method_name` is the name of the method on `self.k` (pykrakenapi instance).
        """
        if not self.k:
            logger.error("KrakenAPI client (pykrakenapi) is not initialized. Cannot make API call.")
            return {"error": ["Client not initialized due to missing API keys."]}

        method_to_call = getattr(self.k, method_name, None)
        if not callable(method_to_call):
            logger.error(f"Method {method_name} not found in pykrakenapi client.")
            return {"error": [f"Internal error: Method {method_name} not available."]}

        for attempt in range(self.rate_limit_retry_attempts):
            try:
                loop = asyncio.get_event_loop()
                raw_result = await loop.run_in_executor(None, lambda: method_to_call(*args, **kwargs))
                
                api_response = {}

                if isinstance(raw_result, dict):
                    api_response = raw_result
                elif isinstance(raw_result, tuple) and len(raw_result) == 2:
                    df_part, second_part = raw_result
                    if isinstance(second_part, dict):
                        api_response = second_part
                        if not api_response.get('error') and 'result' not in api_response:
                            api_response['result'] = {} 
                    elif method_name == "get_ohlc_data" and isinstance(df_part, pd.DataFrame) and isinstance(second_part, int):
                        api_response = {
                            'result': {
                                'ohlc_records': df_part.to_dict(orient='records'),
                                'last': second_part
                            },
                            'error': []
                        }
                    else:
                        logger.error(f"Unexpected tuple structure from {method_name}: ({type(df_part)}, {type(second_part)})")
                        raise KrakenAPIError(f"Unexpected tuple output from {method_name}", errors=[f"Tuple types: {type(df_part)}, {type(second_part)}"])
                elif isinstance(raw_result, pd.DataFrame):
                    logger.warning(f"Received direct DataFrame from {method_name}. Attempting conversion.")
                    if method_name == "get_account_balance":
                        balances_dict = raw_result.iloc[:, 0].to_dict() if not raw_result.empty and raw_result.shape[1] > 0 else {}
                        api_response = {'result': balances_dict, 'error': []}
                    elif method_name == "get_ticker_information":
                        ticker_dict = raw_result.to_dict(orient='index')
                        api_response = {'result': ticker_dict, 'error': []}
                    else: 
                        api_response = {'result': raw_result.to_dict(orient='records'), 'error': []}
                else:
                    logger.error(f"Unhandled result type from pykrakenapi method {method_name}: {type(raw_result)}")
                    raise KrakenAPIError(f"Unhandled result type from {method_name}", errors=[f"Got {type(raw_result)}"])
                
                if api_response.get("error"):
                    errors = api_response["error"]
                    if any("Rate limit" in e for e in errors) or any("Unavailable" in e for e in errors):
                        if attempt < self.rate_limit_retry_attempts - 1:
                            logger.warning(f"Rate limit hit on attempt {attempt+1} for {method_name}. Retrying in {self.rate_limit_retry_delay}s... Errors: {errors}")
                            await asyncio.sleep(self.rate_limit_retry_delay * (attempt + 1)) 
                            continue
                        else:
                            logger.error(f"Rate limit persists after {self.rate_limit_retry_attempts} attempts for {method_name}. Errors: {errors}")
                            raise KrakenAPIError(f"Rate limit exceeded for {method_name}", errors=errors)
                    else:
                        logger.error(f"Kraken API error for {method_name}: {errors}")
                        raise KrakenAPIError(f"API error for {method_name}", errors=errors)
                
                return api_response

            except KrakenAPIError: 
                raise
            except Exception as e:
                logger.exception(f"Unexpected error during API call {method_name} (attempt {attempt+1}): {e}")
                if attempt < self.rate_limit_retry_attempts - 1:
                    await asyncio.sleep(self.rate_limit_retry_delay)
                else:
                    raise KrakenAPIError(f"Unexpected error in {method_name} after retries: {str(e)}", errors=[str(e)])
        
        return {"error": [f"Failed {method_name} after {self.rate_limit_retry_attempts} attempts."]}

    async def get_account_balance(self) -> dict:
        """Fetches the current account balance from Kraken."""
        logger.info("Fetching account balance...")
        if not self.k:
             logger.error("Cannot fetch account balance: Kraken client not initialized (API key/secret missing).")
             return {"error": ["API client not initialized."], "result": {}}
        try:
            response_dict = await self._make_api_call("get_account_balance")
            return response_dict
        except KrakenAPIError as e:
            return {"error": e.errors, "result": {}}
        except Exception as e:
            logger.exception("Unexpected error in get_account_balance wrapper.")
            return {"error": [str(e)], "result": {}}

    async def get_ticker_information(self, pair: str | list[str] | None = None) -> dict:
        """Fetches ticker information for a given trading pair, list of pairs, or all pairs if None."""
        log_msg = "Fetching ticker information for all pairs..."
        if isinstance(pair, str):
            log_msg = f"Fetching ticker information for pair: {pair}..."
        elif isinstance(pair, list):
            log_msg = f"Fetching ticker information for pairs: {', '.join(pair)}..."
        logger.info(log_msg)
        
        if not self.k:
            logger.warning("Kraken client not initialized. Returning mock ticker data.")
            mock_pair_key = pair if isinstance(pair, str) else "XXBTZUSD" 
            return {"error": ["API client not initialized."], "result": {mock_pair_key: {"c": ["50000.00", "0.1"], "v": ["1000.00", "2000.00"]}}}
        try:
            response_dict = await self._make_api_call("get_ticker_information", pair=pair)
            return response_dict
        except KrakenAPIError as e:
            return {"error": e.errors, "result": {}}
        except Exception as e:
            logger.exception(f"Unexpected error in get_ticker_information wrapper for {pair}.")
            return {"error": [str(e)], "result": {}}

    async def get_ohlc_data(self, pair: str, interval: int = 1, since: int = None) -> dict:
        """Fetches OHLC data."""
        logger.info(f"Fetching OHLC data for {pair} with interval {interval} min, since {since or 'start'}...")
        if not self.k:
            return {"error": ["API client not initialized."]}
        try:
            return await self._make_api_call("get_ohlc_data", pair=pair, interval=interval, since=since)
        except KrakenAPIError as e:
            return {"error": e.errors, "result": {}}
        except Exception as e:
            logger.exception(f"Unexpected error in get_ohlc_data for {pair}.")
            return {"error": [str(e)], "result": {}}

    async def place_order(self, pair: str, order_type: str, side: str, volume: str, price: str = None) -> dict:
        """Places an order on Kraken."""
        logger.info(f"Placing order: {side} {volume} {pair} at {price if price else 'market'}")
        if not self.k:
             return {"error": ["API client not initialized."]}
        
        params = {'pair': pair, 'type': side, 'ordertype': order_type, 'volume': volume}
        if price and order_type == 'limit':
            params['price'] = price
        
        try:
            return await self._make_api_call("add_standard_order", **params)
        except KrakenAPIError as e:
            return {"error": e.errors, "result": {}}
        except Exception as e:
            logger.exception(f"Unexpected error in place_order for {pair}.")
            return {"error": [str(e)], "result": {}}
