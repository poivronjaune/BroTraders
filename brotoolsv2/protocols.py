"""
brotoolsv2.protocols

Shared data contracts between strategies, the risk manager, and the order
manager. Kept separate from any single strategy module so none of these
components need to import a concrete strategy class to get shared types.
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class Signal:
    """
    Emitted by a Strategy's on_bar() when its entry conditions are met.

    Strategies are pure-logic and have no access to live account equity,
    so quantity is intentionally left unset here. risk_manager.py computes
    and fills in quantity (based on equity, risk %, and stop distance)
    before the signal is passed to order_manager.py.
    """
    strategy_name: str
    symbol: str
    entry_price: float
    stop_price: float
    target_price: float
    reason: str
    signal_time: datetime
    quantity: int | None = None

    