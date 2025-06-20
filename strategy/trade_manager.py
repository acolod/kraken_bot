# strategy/trade_manager.py - v0.2.2 (Improved Sizing and Validation)
import logging
from kraken.client import KrakenClient

logger = logging.getLogger(__name__)

class TradeManager:
    """
    Manages active trades, including placing orders with conditional closes,
    monitoring positions, and handling trade lifecycle events.
    """
    def __init__(self, kraken_client: KrakenClient):
        self.kraken_client = kraken_client
        self.active_trades = {}
        logger.info("TradeManager initialized.")

    def _calculate_trade_volume(self, strategy_params: dict) -> float:
        """
        (Future Implementation)
        Calculates the trade volume based on risk parameters.
        For now, returns a fixed USD value to trade.
        """
        # Placeholder: This should eventually calculate volume based on account balance
        # and risk percentage. For now, we calculate how many units to buy for a
        # fixed $20 trade size.
        
        entry_price = strategy_params.get("entry", 0)
        if entry_price <= 0:
            return 0.0

        fixed_usd_amount = 20.0  # Trade with $20 for now
        volume = fixed_usd_amount / entry_price
        
        return volume

    async def execute_strategy(self, strategy_params: dict) -> dict:
        """
        Executes a trading strategy by placing an entry order with a conditional stop-loss.
        """
        logger.info(f"Executing strategy: {strategy_params}")

        if not all(k in strategy_params for k in ['pair', 'side', 'entry', 'stop_loss']):
            error_msg = "Strategy parameters are missing required keys."
            logger.error(error_msg)
            return {"error": [error_msg]}

        # Calculate a more reasonable trade volume
        trade_volume = self._calculate_trade_volume(strategy_params)
        if trade_volume == 0.0:
            return {"error": ["Could not calculate trade volume due to invalid entry price."]}

        pair = strategy_params['pair']
        side = strategy_params['side']
        entry_price = str(strategy_params['entry'])
        stop_loss_price = str(strategy_params['stop_loss'])
        volume = f"{trade_volume:.8f}" # Format volume to 8 decimal places

        order_params = {
            'pair': pair,
            'type': side,
            'ordertype': 'limit',
            'price': entry_price,
            'volume': volume,
            'close_ordertype': 'stop-loss',
            'close_price': stop_loss_price,
            'validate': True # IMPORTANT: Set to True for testing.
        }

        logger.info(f"Placing order with params: {order_params}")
        
        order_result = await self.kraken_client.place_order(**order_params)
        
        logger.info(f"Order placement result: {order_result}")
        
        return order_result

    async def monitor_active_trades(self):
        """(Future) Monitors active trades for take-profit management."""
        pass