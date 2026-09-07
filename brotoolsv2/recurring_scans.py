"""
Recurring scanner coordination for the v2 trading session.

The coordinator owns scan timing and watchlist updates, while a provider
owns the IBKR-specific scanner call. This keeps Sunday/offline development
and unit tests deterministic without using a mock IBKR module.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime
from typing import Protocol
from zoneinfo import ZoneInfo

import pandas as pd
from ib_async import IB, ScannerSubscription

from brotoolsv2.watchlist import Watchlist

logger = logging.getLogger(__name__)

EASTERN = ZoneInfo("America/New_York")


class ScanProvider(Protocol):
    async def scan(self, subscription: ScannerSubscription) -> pd.DataFrame:
        """Return normalized scanner rows containing at least ``symbol``."""


class IBKRScanProvider:
    """Production scanner provider backed by one persistent ib_async connection."""

    def __init__(self, ib: IB):
        self.ib = ib

    async def scan(self, subscription: ScannerSubscription) -> pd.DataFrame:
        results = await self.ib.reqScannerDataAsync(subscription)
        rows = []
        for result in results:
            contract = getattr(result, "contractDetails", None)
            contract = getattr(contract, "contract", contract)
            symbol = getattr(contract, "symbol", None)
            if symbol:
                rows.append(
                    {
                        "symbol": symbol,
                        "rank": getattr(result, "rank", None),
                        "distance": getattr(result, "distance", None),
                        "benchmark": getattr(result, "benchmark", None),
                        "projection": getattr(result, "projection", None),
                        "legs": getattr(result, "legsStr", None),
                    }
                )
        return pd.DataFrame(rows, columns=["symbol", "rank", "distance", "benchmark", "projection", "legs"])


def is_market_day(now: datetime) -> bool:
    """
    Return whether scans may run on this weekday.

    The first implementation deliberately handles the Sunday/weekend case
    without adding a calendar dependency. Exchange holidays can be added to
    this predicate later without changing the coordinator.
    """
    if now.tzinfo is None:
        now = now.replace(tzinfo=EASTERN)
    return now.astimezone(EASTERN).weekday() < 5


class StrategyLike(Protocol):
    name: str

    def scanner(self) -> ScannerSubscription:
        ...

    def on_scan_results(self, df_scan: pd.DataFrame) -> list[str]:
        ...


class RecurringScanner:
    """Runs all active strategy scanners and merges candidates into one watchlist."""

    def __init__(
        self,
        strategies: Sequence[StrategyLike],
        watchlist: Watchlist,
        provider: ScanProvider,
        interval_seconds: float = 300.0,
        market_day: Callable[[datetime], bool] = is_market_day,
    ):
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be greater than zero")
        self.strategies = tuple(strategies)
        self.watchlist = watchlist
        self.provider = provider
        self.interval_seconds = interval_seconds
        self.market_day = market_day

    async def run_cycle(self, now: datetime | None = None) -> dict[str, int]:
        """Run one scan cycle and return the number of candidates per strategy."""
        scan_time = now or datetime.now(tz=EASTERN)
        if not self.market_day(scan_time):
            logger.info("⏸️  Skipping scanner cycle while the market is closed.")
            return {}

        counts: dict[str, int] = {}
        for strategy in self.strategies:
            try:
                scan = await self.provider.scan(strategy.scanner())
                symbols = strategy.on_scan_results(scan)
                count = 0
                seen_symbols: set[str] = set()
                for symbol in symbols:
                    if not isinstance(symbol, str) or not symbol.strip():
                        logger.warning(
                            "⚠️  Strategy %s returned an invalid scanner symbol: %r",
                            strategy.name,
                            symbol,
                        )
                        continue
                    normalized_symbol = symbol.strip().upper()
                    if normalized_symbol in seen_symbols:
                        continue
                    seen_symbols.add(normalized_symbol)
                    self.watchlist.add_candidate(normalized_symbol, strategy.name)
                    count += 1
                counts[strategy.name] = count
                logger.info("🔎 %s scan added %d candidates.", strategy.name, count)
            except Exception:
                logger.exception("❌ Scanner cycle failed for strategy %s.", strategy.name)
                counts[strategy.name] = 0
        return counts

    async def run(self, stop_event: asyncio.Event) -> None:
        """Run scan cycles until ``stop_event`` is set."""
        while not stop_event.is_set():
            await self.run_cycle()
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=self.interval_seconds)
            except asyncio.TimeoutError:
                continue
