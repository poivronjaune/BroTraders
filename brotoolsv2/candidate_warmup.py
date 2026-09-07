"""Warm historical data for symbols newly added to the shared watchlist."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Protocol

from brotoolsv2.watchlist import Watchlist

logger = logging.getLogger(__name__)


class DataWarmer(Protocol):
    async def warm_up_symbol(self, symbol: str) -> None:
        """Fetch historical bars and start the symbol's live subscription."""


class CandidateWarmup:
    """Coordinate one-time historical warm-up for watchlist candidates."""

    def __init__(
        self,
        watchlist: Watchlist,
        data_manager: DataWarmer,
        warm_up: Callable[[str], Awaitable[None]] | None = None,
    ) -> None:
        self.watchlist = watchlist
        self.data_manager = data_manager
        self._warm_up = warm_up or data_manager.warm_up_symbol
        self._warmed_symbols: set[str] = set()

    async def run_cycle(self) -> dict[str, bool]:
        """
        Warm each candidate that has not succeeded before.

        A failed symbol is not marked as warmed, so a later cycle can retry it.
        Failures are isolated per symbol and reported as ``False``.
        """
        results: dict[str, bool] = {}
        for symbol in self.watchlist.get_candidate_symbols():
            if symbol in self._warmed_symbols:
                continue

            try:
                await self._warm_up(symbol)
            except Exception:
                logger.exception("❌ Historical warm-up failed for %s.", symbol)
                results[symbol] = False
                continue

            self._warmed_symbols.add(symbol)
            results[symbol] = True
            logger.info("📚 Historical data warmed up for %s.", symbol)

        return results
