"""
brotoolsv2.data_manager

Owns per-symbol historical + live 1-minute bar data. Uses one shared IB
connection (passed in by bot_session.py, not created here) and one
keepUpToDate=True subscription per symbol - ib_async delivers the 2-day
historical warm-up first, then seamlessly continues with live bars on
the same subscription.

IBKR aggregates ticks into 1-min bars server-side. ib.barUpdateEvent
fires on every partial tick of the forming last bar (hasNewBar=False)
and again when a bar actually closes and a new one starts forming
(hasNewBar=True). We only act on hasNewBar=True, and even then we drop
the newly-appended (still forming, incomplete) last bar before storing
and announcing the data, so strategies only ever see fully closed
candles.

data_manager has no knowledge of strategies. It only fetches, holds, and
announces new bars via bar_ready_event; bot_session.py is responsible for
reacting to that event and calling into strategies.
"""

import logging

import pandas as pd
from ib_async import IB, Stock, util, Event

logger = logging.getLogger(__name__)


class DataManager:
    def __init__(self, ib: IB):
        self.ib = ib
        self.dataframes: dict[str, pd.DataFrame] = {}
        self._bars_by_symbol: dict = {}   # symbol -> live BarDataList
        self.bar_ready_event = Event("bar_ready_event")
        self.ib.barUpdateEvent += self._on_bar_update

    async def warm_up_symbol(self, symbol: str) -> None:
        """
        Fetches 2 days of 1-min bars (pre-market included) for a symbol
        and starts a live keepUpToDate subscription in the same call.
        Safe to call once per symbol - calling it again for a symbol
        already warmed up will create a duplicate subscription, so the
        caller (bot_session) is responsible for only warming up new
        candidates once.
        """
        contract = Stock(symbol, "SMART", "USD")
        await self.ib.qualifyContractsAsync(contract)

        bars = await self.ib.reqHistoricalDataAsync(
            contract,
            endDateTime="",
            durationStr="2 D",
            barSizeSetting="1 min",
            whatToShow="TRADES",
            useRTH=False,
            keepUpToDate=True,
        )

        self._bars_by_symbol[symbol] = bars
        self.dataframes[symbol] = self._bars_to_df(bars)
        logger.info(f"📡 {symbol} warmed up ({len(bars)} bars) and live-subscribed.")

    def _on_bar_update(self, bars, hasNewBar: bool) -> None:
        """
        Fires on every partial tick of the live subscription, but we only
        act when hasNewBar=True - meaning the previous bar just closed
        and a new (still-forming, incomplete) bar was appended. We store
        and announce everything up to but excluding that new incomplete
        bar, so strategies always see a fully closed last candle.
        """
        if not hasNewBar:
            return

        symbol = bars.contract.symbol
        if self._bars_by_symbol.get(symbol) is not bars:
            return  # defensive: not a subscription this instance owns

        full_df = self._bars_to_df(bars)
        closed_df = full_df.iloc[:-1]  # drop the newly-forming incomplete bar

        self.dataframes[symbol] = closed_df
        logger.info(f"🕐 {symbol} new 1-min bar closed.")
        self.bar_ready_event.emit(symbol, closed_df)

    @staticmethod
    def _bars_to_df(bars) -> pd.DataFrame:
        df = util.df(bars)
        df = df.set_index("date")
        return df
