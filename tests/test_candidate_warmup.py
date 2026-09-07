import asyncio

from brotoolsv2.candidate_warmup import CandidateWarmup
from brotoolsv2.watchlist import Watchlist


class FakeDataManager:
    def __init__(self, failures=None):
        self.calls = []
        self.failures = set(failures or ())

    async def warm_up_symbol(self, symbol):
        self.calls.append(symbol)
        if symbol in self.failures:
            self.failures.remove(symbol)
            raise RuntimeError("historical data unavailable")


def run(coroutine):
    return asyncio.run(coroutine)


def test_warm_up_cycle_processes_each_candidate_once():
    watchlist = Watchlist()
    watchlist.add_candidate("MSFT", "gap-rise")
    watchlist.add_candidate("AAPL", "oversold-vwap")
    watchlist.add_candidate("MSFT", "oversold-vwap")
    data_manager = FakeDataManager()
    warmup = CandidateWarmup(watchlist, data_manager)

    assert run(warmup.run_cycle()) == {"AAPL": True, "MSFT": True}
    assert run(warmup.run_cycle()) == {}
    assert data_manager.calls == ["AAPL", "MSFT"]


def test_failed_warm_up_isolated_and_retried():
    watchlist = Watchlist()
    watchlist.add_candidate("AAPL", "gap-rise")
    watchlist.add_candidate("TSLA", "oversold-vwap")
    data_manager = FakeDataManager(failures={"AAPL"})
    warmup = CandidateWarmup(watchlist, data_manager)

    assert run(warmup.run_cycle()) == {"AAPL": False, "TSLA": True}
    assert run(warmup.run_cycle()) == {"AAPL": True}
    assert data_manager.calls == ["AAPL", "TSLA", "AAPL"]
