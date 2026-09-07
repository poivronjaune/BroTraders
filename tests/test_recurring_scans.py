import asyncio
from datetime import datetime

import pandas as pd

from brotoolsv2.recurring_scans import RecurringScanner
from brotoolsv2.watchlist import Watchlist


class FakeStrategy:
    def __init__(self, name, symbols):
        self.name = name
        self.symbols = symbols
        self.scans = 0

    def scanner(self):
        return self.name

    def on_scan_results(self, df_scan):
        self.scans += 1
        return self.symbols


class FakeProvider:
    def __init__(self, frames=None, error=False):
        self.frames = list(frames or [])
        self.error = error
        self.subscriptions = []

    async def scan(self, subscription):
        self.subscriptions.append(subscription)
        if self.error:
            raise RuntimeError("scanner unavailable")
        return self.frames.pop(0) if self.frames else pd.DataFrame(columns=["symbol"])


def run(coroutine):
    return asyncio.run(coroutine)


def test_closed_market_skips_all_strategies():
    strategy = FakeStrategy("gap-rise", ["AAPL"])
    provider = FakeProvider([pd.DataFrame({"symbol": ["AAPL"]})])
    watchlist = Watchlist()
    scanner = RecurringScanner([strategy], watchlist, provider)

    result = run(scanner.run_cycle(datetime(2026, 9, 6, 12, 0)))

    assert result == {}
    assert strategy.scans == 0
    assert provider.subscriptions == []
    assert watchlist.get_candidate_strategies("AAPL") == set()


def test_active_strategies_share_watchlist_and_normalize_symbols():
    first = FakeStrategy("gap-rise", ["aapl", "MSFT", "AAPL"])
    second = FakeStrategy("oversold-vwap", ["MSFT", "NVDA"])
    provider = FakeProvider(
        [
            pd.DataFrame({"symbol": ["AAPL", "MSFT"]}),
            pd.DataFrame({"symbol": ["MSFT", "NVDA"]}),
        ]
    )
    watchlist = Watchlist()
    scanner = RecurringScanner([first, second], watchlist, provider)

    result = run(scanner.run_cycle(datetime(2026, 9, 7, 10, 0)))

    assert result == {"gap-rise": 2, "oversold-vwap": 2}
    assert watchlist.get_candidate_strategies("AAPL") == {"gap-rise"}
    assert watchlist.get_candidate_strategies("MSFT") == {"gap-rise", "oversold-vwap"}
    assert watchlist.get_candidate_strategies("NVDA") == {"oversold-vwap"}


def test_empty_scan_and_provider_error_do_not_stop_other_strategies():
    empty = FakeStrategy("empty", [])
    working = FakeStrategy("working", ["TSLA"])
    provider = FakeProvider([pd.DataFrame(columns=["symbol"]), pd.DataFrame({"symbol": ["TSLA"]})])
    watchlist = Watchlist()
    scanner = RecurringScanner([empty, working], watchlist, provider)

    result = run(scanner.run_cycle(datetime(2026, 9, 7, 10, 0)))

    assert result == {"empty": 0, "working": 1}
    assert watchlist.get_candidate_strategies("TSLA") == {"working"}

    failing = RecurringScanner([empty, working], watchlist, FakeProvider(error=True))
    result = run(failing.run_cycle(datetime(2026, 9, 7, 10, 0)))
    assert result == {"empty": 0, "working": 0}
