"""
data_manager.py

DataManager — owns the per-symbol price data during a live session.

Phase 3 (initialisation): for each watch-list symbol, fetch 2 days of 1-minute
bars with ``keepUpToDate=True`` so the same subscription seamlessly continues
delivering live bars. The historical frame is pre-loaded with the strategy's
indicators.

Phase 4 (live data): IBKR fires the subscription's ``updateEvent`` whenever the
forming bar updates. When ``hasNewBar`` is True a bar has just been *confirmed*,
so the DataManager rebuilds the symbol's DataFrame, re-runs the strategy's
indicators, and invokes the registered bar callback with ``(symbol, df)``.
"""

import asyncio
import logging
from typing import Awaitable, Callable

import pandas as pd
from ib_async import IB, Stock, util

logger = logging.getLogger(__name__)

# Signature of the callback fired on every confirmed bar.
BarCallback = Callable[[str, pd.DataFrame], Awaitable[None]]


class DataManager:
    def __init__(self, ib: IB, strategy) -> None:
        self.ib = ib
        self.strategy = strategy
        self._frames: dict[str, pd.DataFrame] = {}
        self._bars: dict[str, object] = {}       # symbol -> BarDataList
        self._contracts: dict[str, Stock] = {}
        self._bar_callback: BarCallback | None = None

    # ------------------------------------------------------------------
    def set_bar_callback(self, callback: BarCallback) -> None:
        """Register the async handler called on each confirmed bar."""
        self._bar_callback = callback

    def frame(self, symbol: str) -> pd.DataFrame | None:
        return self._frames.get(symbol)

    @property
    def symbols(self) -> list[str]:
        return list(self._frames.keys())

    # ------------------------------------------------------------------
    # Phase 3 — historical fetch + live subscription
    # ------------------------------------------------------------------
    async def initialize(self, symbols: list[str]) -> None:
        """Fetch warm history and subscribe to live bars for each symbol."""
        for symbol in symbols:
            try:
                contract = Stock(symbol, "SMART", "USD")
                await self.ib.qualifyContractsAsync(contract)

                bars = await self.ib.reqHistoricalDataAsync(
                    contract,
                    endDateTime="",
                    durationStr="2 D",
                    barSizeSetting="1 min",
                    whatToShow="TRADES",
                    useRTH=False,          # pre-market needed for gap detection
                    keepUpToDate=True,     # keep delivering live bars
                )

                if not bars:
                    logger.warning("⚠️  No historical data for %s — skipping.", symbol)
                    continue

                self._contracts[symbol] = contract
                self._bars[symbol] = bars
                self._frames[symbol] = self._build_frame(symbol, bars)

                # Subscribe to live updates for this symbol's subscription.
                bars.updateEvent += self._make_handler(symbol)
                logger.info("📈 %s initialised (%d bars) and subscribed.", symbol, len(bars))

            except Exception as e:  # noqa: BLE001 — one bad symbol must not abort the session
                logger.error("❌ Failed to initialise %s: %s", symbol, e)

            await asyncio.sleep(0.1)  # IBKR pacing

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _build_frame(self, symbol: str, bars) -> pd.DataFrame:
        """Convert a BarDataList to the indexed DataFrame the strategy expects."""
        df = util.df(bars)
        if "date" in df.columns:
            df = df.set_index("date")
        df.index = pd.DatetimeIndex(df.index)
        df["symbol"] = symbol
        df = self.strategy.add_indicators(df)
        return df

    def _make_handler(self, symbol: str):
        """Build a sync updateEvent handler that schedules async processing."""
        def handler(bars, hasNewBar):
            # Only act when a bar has just been confirmed (closed).
            if hasNewBar:
                asyncio.ensure_future(self._on_new_bar(symbol, bars))
        return handler

    async def _on_new_bar(self, symbol: str, bars) -> None:
        try:
            df = self._build_frame(symbol, bars)
            self._frames[symbol] = df
        except Exception as e:  # noqa: BLE001
            logger.error("❌ Indicator update failed for %s: %s", symbol, e)
            return

        if self._bar_callback is not None:
            await self._bar_callback(symbol, df)
