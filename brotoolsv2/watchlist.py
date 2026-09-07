"""
brotoolsv2.watchlist

Global, shared watchlist and symbol-locking registry. One instance is
created at session startup and passed to data_manager, risk_manager, and
order_manager so all components see the same locking state.

A symbol can be flagged as a candidate by more than one active strategy
at once, but once a position is pending, open, or closing on that
symbol, it is locked to the strategy that placed it - all other
strategies must skip it until the position is fully closed (status
returns to 'flat').
"""

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Statuses where the symbol is unavailable for any other strategy to act on
LOCKED_STATUSES = {"pending_entry", "open", "closing"}


@dataclass
class WatchlistEntry:
    symbol: str
    candidate_strategies: set = field(default_factory=set)
    owning_strategy: str | None = None
    status: str = "flat"


class Watchlist:
    def __init__(self):
        self._entries: dict[str, WatchlistEntry] = {}

    def add_candidate(self, symbol: str, strategy_name: str) -> None:
        """Flags a symbol as a candidate for a given strategy. Safe to call repeatedly."""
        entry = self._entries.setdefault(symbol, WatchlistEntry(symbol=symbol))
        entry.candidate_strategies.add(strategy_name)

    def get_candidate_strategies(self, symbol: str) -> set:
        entry = self._entries.get(symbol)
        return entry.candidate_strategies if entry else set()

    def get_candidate_symbols(self) -> tuple[str, ...]:
        """Return all symbols currently flagged by at least one strategy."""
        return tuple(
            sorted(
                symbol
                for symbol, entry in self._entries.items()
                if entry.candidate_strategies
            )
        )

    def is_locked(self, symbol: str) -> bool:
        """True if this symbol currently has a pending/open/closing position."""
        entry = self._entries.get(symbol)
        return entry is not None and entry.status in LOCKED_STATUSES

    def try_lock(self, symbol: str, strategy_name: str) -> bool:
        """
        Attempts to lock a symbol to strategy_name by moving it to
        'pending_entry'. Returns False if already locked under any
        strategy. Call this at order-placement time, not at signal
        detection time.
        """
        entry = self._entries.setdefault(symbol, WatchlistEntry(symbol=symbol))

        if entry.status in LOCKED_STATUSES:
            logger.warning(
                f"⚠️  {symbol} lock attempt by {strategy_name} rejected - "
                f"already {entry.status} under {entry.owning_strategy}."
            )
            return False

        entry.owning_strategy = strategy_name
        entry.status = "pending_entry"
        logger.info(f"🔒 {symbol} locked to {strategy_name} (pending_entry).")
        return True

    def mark_open(self, symbol: str) -> None:
        """Called once the entry order is confirmed filled."""
        entry = self._entries.get(symbol)
        if entry is None:
            logger.warning(f"⚠️  mark_open called for {symbol} with no watchlist entry.")
            return
        entry.status = "open"

    def mark_closing(self, symbol: str) -> None:
        """Called when an exit order (stop or target) has been triggered/submitted."""
        entry = self._entries.get(symbol)
        if entry is None:
            logger.warning(f"⚠️  mark_closing called for {symbol} with no watchlist entry.")
            return
        entry.status = "closing"

    def release(self, symbol: str) -> None:
        """
        Called once a position is fully closed. Unlocks the symbol
        (status -> 'flat', owning_strategy -> None).
        """
        entry = self._entries.get(symbol)
        if entry is None:
            logger.warning(f"⚠️  release called for {symbol} with no watchlist entry.")
            return
        entry.owning_strategy = None
        entry.status = "flat"
        logger.info(f"🔓 {symbol} released - back to flat.")

    def get_status(self, symbol: str) -> str:
        entry = self._entries.get(symbol)
        return entry.status if entry else "flat"

    def get_owning_strategy(self, symbol: str):
        entry = self._entries.get(symbol)
        return entry.owning_strategy if entry else None