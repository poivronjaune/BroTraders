from typing import Protocol, runtime_checkable

import pandas as pd
from ib_async import ScannerSubscription

from brotools.trade_signal import Signal


@runtime_checkable
class StrategyProtocol(Protocol):
    """Structural contract the live bot and services rely on.

    ``scanner`` is the minimum required by ``services.py``. The remaining
    members describe the extended live-session interface implemented by
    ``BaseStrategy`` (and therefore by any strategy that subclasses it).
    """

    # Identity
    name: str

    # Session window / risk attributes
    session_start_time: str
    session_end_time: str
    entry_cutoff_time: str
    max_positions: int
    close_on_session_end: bool

    # Market logic
    def scanner(self) -> ScannerSubscription: ...
    def add_indicators(self, df_data: pd.DataFrame) -> pd.DataFrame: ...
    def is_buy_signal(self, df_data: pd.DataFrame) -> dict: ...

    # Session hooks
    def on_scan_results(self, df_scan: pd.DataFrame | None) -> list[str]: ...
    def on_bar(self, symbol: str, df: pd.DataFrame, positions) -> "Signal | None": ...
    def on_fill(self, symbol: str, fill) -> None: ...
    def is_session_done(self) -> bool: ...
