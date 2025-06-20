# kraken/client.py - v0.2.1 (Execution Fix)
import logging
import krakenex
from pykrakenapi import KrakenAPI
import asyncio
import time
import pandas as pd

logger = logging.getLogger(__name__)

class KrakenAPIError(Exception):
    """Custom exception for Kraken API errors."""
    def __init__(self, message, errors=None):
        super().__init__(message)
        self.errors = errors if errors is not None else []

class RateLimiter:
    """A simple async token bucket rate limiter."""
    def __init__(self, requests_per_period, period_seconds):
        self.requests_per_period = requests_per_period
        self.period_seconds = period_seconds
        self.tokens = self.requests_per_period
        self.last_refill_time = time.monotonic()
        self.lock = asyncio.Lock()

    async def wait_for_token(self):
        async with self.lock:
            now = time.monotonic()
            elapsed = now - self.last_refill_time

            if elapsed > self.period_seconds:
                self.tokens = self.requests_per_period
                self.last_refill_time = now

            if self.tokens == 0:
                time_to_wait = self.period_seconds / self.requests_per_period
                logger.warning(f"Rate limit reached. Sleeping for {time_to_wait:.2f} seconds.")
                await asyncio.sleep(time_to_wait)
                self.tokens += 1
                self.last_refill_time = time.monotonic()
            
            self.tokens -= 1

class KrakenClient:
    """
    Handles all API interactions with the Kraken exchange.
    Includes a rate limiter to prevent API spam.
    """
    def __init__(self, api_key: str, private_key: str):
        self.api_key = api_key
        self.private_key = private_key
        
        self.rate_limiter = RateLimiter(requests_per_period=1, period_seconds=1.5)
        
        if not api_key or not private_key:
            logger.warning("Kraken API key or private key is not set. Authenticated calls will fail.")
            self.kraken = None
            self.k = None
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
        Makes an API call with our internal rate limiter.
        """
        await self.rate_limiter.wait_for_token()

        if not self.k:
            logger.error("KrakenAPI client (pykrakenapi) is not initialized.")
            return {"error": ["Client not initialized due to missing API keys."]}

        method_to_call = getattr(self.k, method_name, None)
        if not callable(method_to_call):
            logger.error(f"Method {method_name} not found in pykrakenapi client.")
            return {"error": [f"Internal error: Method {method_name} not available."]}

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
                    api_response = {'result': {'ohlc_records': df_part.to_dict(orient='records'),'last': second_part}, 'error': []}
                else:
                    raise KrakenAPIError(f"Unexpected tuple output from {method_name}")
            elif isinstance(raw_result, pd.DataFrame):
                if method_name == "get_account_balance":
                    balances_dict = raw_result.iloc[:, 0].to_dict() if not raw_result.empty else {}
                    api_response = {'result': balances_dict, 'error': []}
                elif method_name == "get_ticker_information":
                    ticker_dict = raw_result.to_dict(orient='index')
                    api_response = {'result': ticker_dict, 'error': []}
                else: 
                    api_response = {'result': raw_result.to_dict(orient='records'), 'error': []}
            else:
                raise KrakenAPIError(f"Unhandled result type from {method_name}: {type(raw_result)}")
            
            if api_response.get("error"):
                raise KrakenAPIError(f"API error for {method_name}", errors=api_response["error"])
            
            return api_response

        except Exception as e:
            logger.exception(f"Unexpected error during API call {method_name}: {e}")
            raise KrakenAPIError(f"Unexpected error in {method_name}: {str(e)}", errors=[str(e)])

    async def get_account_balance(self) -> dict:
        """Fetches the current account balance from Kraken."""
        logger.info("Fetching account balance...")
        if not self.k:
             return {"error": ["API client not initialized."], "result": {}}
        try:
            return await self._make_api_call("get_account_balance")
        except KrakenAPIError as e:
            return {"error": e.errors, "result": {}}

    async def get_ticker_information(self, pair: str | list[str] | None = None) -> dict:
        """Fetches ticker information for a given trading pair(s)."""
        logger.info(f"Fetching ticker information for pair(s): {pair or 'ALL'}...")
        if not self.k:
            mock_pair_key = pair if isinstance(pair, str) else "XXBTZUSD" 
            return {"error": ["API client not initialized."], "result": {mock_pair_key: {"c": ["50000.00", "0.1"], "v": ["1000.00", "2000.00"]}}}
        try:
            return await self._make_api_call("get_ticker_information", pair=pair)
        except KrakenAPIError as e:
            return {"error": e.errors, "result": {}}

    async def get_ohlc_data(self, pair: str, interval: int = 1, since: int = None) -> dict:
        """Fetches OHLC data."""
        logger.info(f"Fetching OHLC data for {pair} with interval {interval} min...")
        if not self.k:
            return {"error": ["API client not initialized."]}
        try:
            return await self._make_api_call("get_ohlc_data", pair=pair, interval=interval, since=since)
        except KrakenAPIError as e:
            return {"error": e.errors, "result": {}}

    async def place_order(self, **kwargs) -> dict:
        """
        Places an order on Kraken. Accepts all keyword arguments and passes them
        to the underlying API library.
        """
        logger.info(f"Placing order with params: {kwargs}")
        if not self.k:
             return {"error": ["API client not initialized."]}
        
        try:
            # We pass all keyword arguments directly to the underlying library function
            return await self._make_api_call("add_standard_order", **kwargs)
        except KrakenAPIError as e:
            return {"error": e.errors, "result": {}}