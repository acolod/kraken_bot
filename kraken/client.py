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
                # pykrakenapi methods are synchronous, so we run them in a thread
                loop = asyncio.get_event_loop()
                # pykrakenapi methods typically return a tuple (DataFrame, dict)
                raw_result = await loop.run_in_executor(None, lambda: method_to_call(*args, **kwargs))
                
                api_response = {}

                if isinstance(raw_result, dict):
                    # Directly a dictionary, likely an error response from pykrakenapi._query
                    api_response = raw_result
                elif isinstance(raw_result, tuple) and len(raw_result) == 2:
                    df_part, second_part = raw_result
                    if isinstance(second_part, dict):
                        # Common case: (DataFrame, dict_response)
                        api_response = second_part
                        # Ensure 'result' key exists if no error, for consistency
                        if not api_response.get('error') and 'result' not in api_response:
                            api_response['result'] = {} 
                    elif method_name == "get_ohlc_data" and isinstance(df_part, pd.DataFrame) and isinstance(second_part, int):
                        # Specific handling for get_ohlc_data: (DataFrame, last_timestamp_int)
                        # We'll convert the DataFrame to a list of dicts for the 'result'.
                        # The pair name is part of kwargs or args, used by Orchestrator to interpret.
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
                    # Handle cases where pykrakenapi might return only a DataFrame (e.g. get_account_balance on success if dict part is empty)
                    logger.warning(f"Received direct DataFrame from {method_name}. Attempting conversion.")
                    if method_name == "get_account_balance":
                        # For balances, Kraken API 'result' is a dict of asset:amount.
                        # pykrakenapi's DataFrame has asset as index, 'vol' as one of the columns.
                        # We need to reconstruct the simple asset:amount dict.
                        # This assumes the DataFrame's first column or a 'vol' column is the balance.
                        # A more robust way is to ensure pykrakenapi always gives the (df, dict_raw_response) tuple.
                        # For now, let's assume the DataFrame index is the asset and it has one primary value column.
                        balances_dict = raw_result.iloc[:, 0].to_dict() if not raw_result.empty and raw_result.shape[1] > 0 else {}
                        api_response = {'result': balances_dict, 'error': []}
                    else: # For other methods, this is less expected.
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
                
                return api_response # Return the dictionary part of the response

            except KrakenAPIError: 
                raise
            except Exception as e:
                logger.exception(f"Unexpected error during API call {method_name} (attempt {attempt+1}): {e}")
                if attempt < self.rate_limit_retry_attempts - 1:
                    await asyncio.sleep(self.rate_limit_retry_delay)
                else:
                    # After all retries, wrap in KrakenAPIError if it's not already one
                    raise KrakenAPIError(f"Unexpected error in {method_name} after retries: {str(e)}", errors=[str(e)])
        
        # Fallback, should ideally be caught by exception handling above
        return {"error": [f"Failed {method_name} after {self.rate_limit_retry_attempts} attempts."]}

    async def get_account_balance(self) -> dict:
        """Fetches the current account balance from Kraken."""
        logger.info("Fetching account balance...")
        if not self.k:
             logger.error("Cannot fetch account balance: Kraken client not initialized (API key/secret missing).")
             return {"error": ["API client not initialized."], "result": {}}
        try:
            # pykrakenapi's get_account_balance returns (DataFrame, dict)
            # _make_api_call is designed to return the dict part.
            response_dict = await self._make_api_call("get_account_balance")
            # The actual balance data is typically under the 'result' key in the dict
            return response_dict # This will include {'error': [], 'result': {...balances...}}
        except KrakenAPIError as e:
            return {"error": e.errors, "result": {}}
        except Exception as e:
            logger.exception("Unexpected error in get_account_balance wrapper.")
            return {"error": [str(e)], "result": {}}

    async def get_ticker_information(self, pair: str) -> dict:
        """Fetches ticker information for a given trading pair."""
        logger.info(f"Fetching ticker information for {pair}...")
        if not self.k:
            logger.warning("Kraken client not initialized. Returning mock ticker data.")
            return {"error": ["API client not initialized."], "result": {pair: {"c": ["50000.00", "0.1"]}}} # Mock structure
        try:
            # pykrakenapi's get_ticker_information returns (DataFrame, dict)
            response_dict = await self._make_api_call("get_ticker_information", pair=pair)
            return response_dict # This will include {'error': [], 'result': {'PAIR': {...ticker_data...}}}
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