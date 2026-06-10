"""
strategy_runner.py

StrategyRunner — the bridge between incoming bars and order placement.

It is registered as the DataManager's bar callback. On every confirmed bar it
asks the strategy for a decision, runs that decision past the RiskManager, and
hands approved signals to the OrderManager. It holds no market logic of its own.
"""

import logging

import pandas as pd

from brotools.order_manager import OrderManager
from brotools.risk_manager import RiskManager

logger = logging.getLogger(__name__)


class StrategyRunner:
    def __init__(self, strategy, order_manager: OrderManager, risk_manager: RiskManager) -> None:
        self.strategy = strategy
        self.order_manager = order_manager
        self.risk_manager = risk_manager

    async def on_bar_ready(self, symbol: str, df: pd.DataFrame) -> None:
        open_symbols = self.order_manager.open_symbols()

        signal = self.strategy.on_bar(symbol, df, open_symbols)
        if signal is None:
            return

        # Use the triggering bar's time for the entry-cutoff check.
        last_time = df.index.max()
        now_str = last_time.strftime("%H:%M") if hasattr(last_time, "strftime") else ""

        approved, reason = self.risk_manager.approve(signal, open_symbols, now_str)
        if not approved:
            logger.info("⛔ %s signal blocked: %s", symbol, reason)
            return

        logger.info("🎯 %s signal approved (%s)", symbol, signal.reason)
        await self.order_manager.place(signal)
