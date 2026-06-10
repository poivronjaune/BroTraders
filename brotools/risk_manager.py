"""
risk_manager.py

RiskManager — a cross-cutting guard. It never generates signals or places
orders; it only approves or blocks them. Every ``Signal`` produced by the
StrategyRunner must pass ``approve()`` before reaching the OrderManager.

Enabled guards (per build decision):
  - Kill switch       : a flag file (DATA/KILL) halts all new trading.
  - Already in position: block a second entry on a held symbol.
  - Max positions     : block once ``strategy.max_positions`` is reached.
  - Entry cutoff       : block new entries after ``strategy.entry_cutoff_time``.

(The daily-loss limit guard is intentionally not enabled for this build.)
"""

import logging
from pathlib import Path

from brotools.config import KILL_SWITCH_FILE
from brotools.trade_signal import Signal

logger = logging.getLogger(__name__)


class RiskManager:
    def __init__(self, strategy, kill_switch_file: str = KILL_SWITCH_FILE) -> None:
        self.strategy = strategy
        self.kill_switch_path = Path(kill_switch_file)

    # ------------------------------------------------------------------
    def kill_switch_active(self) -> bool:
        return self.kill_switch_path.exists()

    # ------------------------------------------------------------------
    def approve(
        self,
        signal: Signal,
        open_symbols: set[str],
        now_str: str,
    ) -> tuple[bool, str]:
        """Return ``(approved, reason)`` for a proposed signal.

        ``now_str`` is the "HH:MM" time of the triggering bar.
        """
        if self.kill_switch_active():
            return False, "kill switch active"

        if signal.symbol in open_symbols:
            return False, "already in position"

        if len(open_symbols) >= self.strategy.max_positions:
            return False, f"max positions reached ({self.strategy.max_positions})"

        if now_str >= self.strategy.entry_cutoff_time:
            return False, f"past entry cutoff ({self.strategy.entry_cutoff_time})"

        return True, "approved"
