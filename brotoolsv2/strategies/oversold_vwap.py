"""
brotoolsv2.strategies.oversold_vwap

Long-only mean-reversion strategy. Scans for the day's biggest % losers
(TOP_PERC_LOSE), then watches for price falling a configurable percentage
below the running RTH VWAP as an entry trigger, betting on a bounce back
toward VWAP.

Pre-market VWAP is computed separately from RTH VWAP purely as a
diagnostic/data-quality column for now (vwap_alignment_threshold_pct is
stored but not yet used in the entry rule - alignment logic is deferred
until real data is available to calibrate it).
"""
import pandas as pd
from datetime import datetime
from ib_async import ScannerSubscription

from brotoolsv2.protocols import Signal
from brotoolsv2.trading_indicators import compute_session_vwap
from brotoolsv2.trading_rules import check_vwap_oversold


class Strategy:
    def __init__(self):
        self.name = "Oversold VWAP Strategy"
        self.description = "Buys stocks that have fallen a threshold percentage below RTH VWAP, targeting a bounce."

        # Read once at startup by strategy_loader.py - no runtime toggling
        self.active = True

        # Session timing - trades all day, unlike gap_rise's open-only window
        self.session_start_time = "09:30"
        self.session_end_time = "16:00"
        self.entry_cutoff_time = "15:30"
        self.close_on_session_end = False

        # Pre-market / RTH windows used for the two separate VWAP calculations
        self.premarket_start_time = "04:00"
        self.premarket_end_time = "09:30"
        self.rth_start_time = "09:30"
        self.rth_end_time = "16:00"

        # Bracket sizing - per-strategy, fixed target
        self.stop_loss_pct = 0.97    # 3% below entry
        self.take_profit_pct = 1.03  # 3% above entry

        # Entry trigger - how far below RTH VWAP counts as oversold
        self.oversold_threshold_pct = 3.0

        # Diagnostic only for now - not yet used to filter/block entries
        self.vwap_alignment_threshold_pct = 2.0

        self.rules = [
            (check_vwap_oversold, {"threshold_pct": self.oversold_threshold_pct, "vwap_column": "rth_vwap"}),
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
        sub.scanCode = 'TOP_PERC_LOSE'
        sub.abovePrice = 10
        sub.belowPrice = 200
        sub.aboveVolume = 100000
        sub.marketCapAbove = 300
        return sub

    def on_scan_results(self, df_scan: pd.DataFrame) -> list:
        """Default: no extra filtering, trade every scanned symbol."""
        return df_scan["symbol"].tolist()

    def add_indicators(self, df_data: pd.DataFrame) -> pd.DataFrame:
        df_data["premarket_vwap"] = compute_session_vwap(
            df_data, self.premarket_start_time, self.premarket_end_time
        )
        df_data["rth_vwap"] = compute_session_vwap(
            df_data, self.rth_start_time, self.rth_end_time
        )

        # Diagnostic column: % difference between the two VWAPs where both exist.
        # Not used in any rule yet - alignment threshold logic is deferred.
        df_data["vwap_diff_pct"] = (
            (df_data["rth_vwap"] - df_data["premarket_vwap"]) / df_data["premarket_vwap"] * 100
        ).round(2)

        return df_data

    def on_bar(self, symbol: str, df_data: pd.DataFrame):
        """
        Called on every new bar for every unlocked symbol on the watchlist.
        """
        all_rules_passed = True
        for rule_func, kwargs in self.rules:
            _, passed = rule_func(df_data, **kwargs)
            if not passed:
                all_rules_passed = False
                break

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
            reason=f"Price {self.oversold_threshold_pct}%+ below RTH VWAP",
            signal_time=signal_time,
        )

    def on_fill(self, symbol: str, fill) -> None:
        """No-op for now - no stop/target adjustment after fills."""
        pass

    def is_session_done(self) -> bool:
        """
        Trades all day. Stops evaluating once entry_cutoff_time has passed.
        """
        now_str = datetime.now().strftime("%H:%M")
        return now_str > self.entry_cutoff_time
    