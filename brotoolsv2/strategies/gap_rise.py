"""
brotoolsv2.strategies.gap_rise

v2 adaptation of the v1 Gap Rise strategy for the persistent, event-driven
bot session. Same entry logic (10%+ overnight gap up, then 3 consecutive
green candles in the 09:30-09:45 window), re-expressed through the v2
Strategy interface.

Locking is handled externally by the watchlist - on_bar() is only ever
called for symbols not already locked to another strategy, so this class
does not track its own "already signaled" state and does not check
position ownership itself.
"""
import pandas as pd
from datetime import datetime
from ib_async import ScannerSubscription

from brotoolsv2.protocols import Signal
from brotoolsv2.trading_indicators import prev_day_closing_bar, current_day_opening_bar
from brotoolsv2.trading_rules import check_trading_window, check_gap_size, check_candles_up


class Strategy:
    def __init__(self):
        self.name = "Gap Rise Strategy"
        self.description = "Identifies stocks with a >10% overnight gap up followed by 3 green candles."

        # Read once at startup by strategy_loader.py - no runtime toggling
        self.active = True

        # Session timing
        self.session_start_time = "09:30"
        self.session_end_time = "16:00"
        self.entry_cutoff_time = "09:45"
        self.close_on_session_end = False

        # Bracket sizing - per-strategy, not shared globally
        self.stop_loss_pct = 0.98    # 2% below entry
        self.take_profit_pct = 1.05  # 5% above entry

        self.gap_threshold = 10
        self.rules = [
            (check_trading_window, {"start_time": "09:30", "end_time": "09:45"}),
            (check_gap_size, {"gap_threshold": 10.0}),
            (check_candles_up, {"consecutive": 3}),
        ]

    def __enter__(self):
        print(f"Opening connection to {self.name}.")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        print(f"Closing connection to {self.name} safely.")

    def scanner(self) -> ScannerSubscription:
        sub = ScannerSubscription()
        sub.numberOfRows = 50
        sub.instrument = 'STK'
        sub.locationCode = 'STK.US.MAJOR'
        sub.scanCode = 'TOP_PERC_GAIN'
        sub.abovePrice = 10
        sub.belowPrice = 200
        sub.aboveVolume = 100000
        sub.marketCapAbove = 300
        return sub

    def on_scan_results(self, df_scan: pd.DataFrame) -> list:
        """Default: no extra filtering, trade every scanned symbol."""
        return df_scan["symbol"].tolist()

    def add_indicators(self, df_data: pd.DataFrame) -> pd.DataFrame:
        prev_close = prev_day_closing_bar(df_data)
        df_data["gap_close_time"] = prev_close.name
        df_data["gap_close_price"] = prev_close["close"]

        curr_open = current_day_opening_bar(df_data)
        df_data["gap_open_time"] = curr_open.name
        df_data["gap_open_price"] = curr_open["open"]

        df_data["gap_size"] = (df_data["gap_open_price"] - df_data["gap_close_price"]).round(2)
        df_data["gap_percent"] = (df_data["gap_size"] / df_data["gap_close_price"] * 100).round(2)

        return df_data

    def on_bar(self, symbol: str, df_data: pd.DataFrame):
        """
        Called on every new bar for every unlocked symbol on the watchlist.
        Folds v1's is_buy_signal() rule evaluation directly in here.
        """
        all_rules_passed = True
        for rule_func, kwargs in self.rules:
            _, passed = rule_func(df_data, **kwargs)
            if not passed:
                all_rules_passed = False
                break

        # Keep exit check seperate from rules evaluation for future flexibility
        if not all_rules_passed:
            return None

        last_candle = df_data.iloc[-1]
        last_time = df_data.index.max()
        entry_price = float(last_candle["close"])
        stop_price = round(entry_price * self.stop_loss_pct, 2)
        target_price = round(entry_price * self.take_profit_pct, 2)

        if isinstance(last_time, datetime):
            signal_time = last_time
        else:
            signal_time = pd.Timestamp(last_time).to_pydatetime()

        return Signal(
            strategy_name=self.name,
            symbol=symbol,
            entry_price=entry_price,
            stop_price=stop_price,
            target_price=target_price,
            reason="10%+ gap up with 3 consecutive green candles",
            signal_time=signal_time,
        )

    def on_fill(self, symbol: str, fill) -> None:
        """No-op for now - gap_rise does not adjust stops/targets after fills."""
        pass

    def is_session_done(self) -> bool:
        """
        This strategy only evaluates during its entry window (09:30-09:45).
        Once entry_cutoff_time has passed, there is nothing left to do.
        """
        now_str = datetime.now().strftime("%H:%M")
        return now_str > self.entry_cutoff_time