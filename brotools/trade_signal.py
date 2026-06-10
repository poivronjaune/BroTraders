"""
trade_signal.py

Typed trade-intent object produced by a strategy's ``on_bar`` method during the
live trading loop. Replaces the ad-hoc ``conditions_trace`` dict that
``is_buy_signal`` returns with a structured object the OrderManager can act on
directly.
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class Signal:
    """A single buy intent emitted by a strategy on a confirmed bar."""

    symbol: str           # ticker symbol
    entry_price: float    # limit price for the entry (parent) order
    stop_price: float     # stop-loss price
    target_price: float   # take-profit price
    quantity: int         # number of shares
    reason: str           # human-readable description of why the signal fired
    signal_time: datetime  # timestamp of the triggering bar
    entry_type: str = "LMT"  # "LMT" = limit entry at entry_price, "MKT" = market entry
