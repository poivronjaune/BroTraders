"""
strategy_base.py

Base class for live-bot strategies. Provides sensible defaults for the extended
strategy interface introduced by the event-driven session architecture so that
concrete strategies (e.g. gap_rise) only need to implement their market logic
(``scanner``, ``add_indicators``, ``is_buy_signal``) and override the few
session attributes that differ from the defaults.

Concrete strategies subclass ``BaseStrategy`` and call ``super().__init__()``.
"""

from abc import ABC, abstractmethod

import pandas as pd
from ib_async import ScannerSubscription

from brotools.trade_signal import Signal


class BaseStrategy(ABC):
    """Default implementation of the live-session strategy contract.

    Subclasses must implement ``scanner``, ``add_indicators`` and
    ``is_buy_signal``. All other methods have working defaults driven by the
    attributes set in ``__init__``.
    """

    def __init__(self) -> None:
        # Identity
        self.name = "Base Strategy"
        self.description = ""

        # --- Session window (Eastern time, "HH:MM") ---
        self.session_start_time = "09:30"   # when the scanner runs
        self.session_end_time   = "16:00"   # when Phase 7 (shutdown) triggers
        self.entry_cutoff_time  = "15:30"   # no new entries after this time

        # --- Risk / sizing ---
        self.max_positions      = 3         # max concurrent open positions
        self.close_on_session_end = False   # leave GTC brackets running by default
        self.default_quantity   = 1         # shares per position
        self.stop_loss_pct      = 0.98      # stop  = entry * 0.98 (2% below)
        self.take_profit_pct    = 1.05      # target = entry * 1.05 (5% above)

        # Internal counter used by the default ``is_session_done``/``on_bar``.
        self._signals_emitted = 0

    # ------------------------------------------------------------------
    # Context manager (kept for parity with the original strategy classes)
    # ------------------------------------------------------------------
    def __enter__(self):
        print(f"Opening connection to {self.name}.")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        print(f"Closing connection to {self.name} safely.")
        return False

    # ------------------------------------------------------------------
    # Market logic — must be implemented by concrete strategies
    # ------------------------------------------------------------------
    @abstractmethod
    def scanner(self) -> ScannerSubscription:
        """Return the IBKR scanner subscription for Phase 2."""

    @abstractmethod
    def add_indicators(self, df_data: pd.DataFrame) -> pd.DataFrame:
        """Add computed indicator columns to a per-symbol DataFrame."""

    @abstractmethod
    def is_buy_signal(self, df_data: pd.DataFrame) -> dict:
        """Evaluate all rules and return a trace dict including ``buy_signal``."""

    # ------------------------------------------------------------------
    # Session hooks — sensible defaults, override as needed
    # ------------------------------------------------------------------
    def on_scan_results(self, df_scan: pd.DataFrame | None) -> list[str]:
        """Filter/rank the raw scan results into a watch list of symbols.

        Default: return every symbol the scanner found.
        """
        if df_scan is None or df_scan.empty or "symbol" not in df_scan.columns:
            return []
        return df_scan["symbol"].tolist()

    def on_bar(self, symbol: str, df: pd.DataFrame, positions) -> Signal | None:
        """Called on every confirmed bar. Return a ``Signal`` or ``None``.

        Default behaviour: delegate to ``is_buy_signal``. If it fires and the
        symbol is not already held, build a bracket ``Signal`` from the signal
        bar's close using ``stop_loss_pct`` / ``take_profit_pct``.
        """
        if symbol in positions:
            return None

        trace = self.is_buy_signal(df)
        if not trace.get("buy_signal"):
            return None

        close = round(float(trace["signal_close"]), 2)
        signal = Signal(
            symbol=symbol,
            entry_price=close,
            stop_price=round(close * self.stop_loss_pct, 2),
            target_price=round(close * self.take_profit_pct, 2),
            quantity=self.default_quantity,
            reason=trace.get("signal_time", "buy_signal"),
            signal_time=df.index.max(),
        )
        self._signals_emitted += 1
        return signal

    def on_fill(self, symbol: str, fill) -> None:
        """Called when any leg of a bracket fills. Default: no-op."""
        return None

    def is_session_done(self) -> bool:
        """Return ``True`` when the strategy has nothing more to do.

        Default: never finishes early; the bot stops at ``session_end_time``.
        """
        return False
