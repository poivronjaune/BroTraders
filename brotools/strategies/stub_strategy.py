# brotools/strategies/stub_strategy.py
"""
Stub strategy — minimal scaffolding to exercise the BaseStrategy contract and
the live-session wiring without producing any trades.

It implements the three abstract methods required by ``BaseStrategy``:
  - ``scanner``        : returns a basic top-losers scan
  - ``add_indicators`` : pass-through (no columns added)
  - ``is_buy_signal``  : always reports no signal

Because ``is_buy_signal`` never fires, the inherited ``on_bar`` never emits a
``Signal``, so the bot will run end-to-end (scan -> data -> loop -> shutdown)
without placing orders. Useful for connection/plumbing tests.
"""

import pandas as pd
from ib_async import ScannerSubscription

from brotools.strategy_base import BaseStrategy


class Strategy(BaseStrategy):
    def __init__(self):
        super().__init__()
        self.name = "Stub Strategy"
        self.description = "Scaffolding strategy that never emits a buy signal."

    def scanner(self) -> ScannerSubscription:
        sub = ScannerSubscription()
        sub.numberOfRows = 50
        sub.instrument = "STK"
        sub.locationCode = "STK.US.MAJOR"
        sub.scanCode = "TOP_PERC_LOSE"
        return sub

    def add_indicators(self, df_data: pd.DataFrame) -> pd.DataFrame:
        # No indicators needed for the stub — return the frame unchanged.
        return df_data

    def is_buy_signal(self, df_data: pd.DataFrame) -> dict:
        symbol = df_data["symbol"].iloc[0] if "symbol" in df_data.columns else "UNKNOWN"
        return {"symbol": symbol, "buy_signal": False}