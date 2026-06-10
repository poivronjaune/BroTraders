"""
order_manager.py

OrderManager — the single component that talks to the IB order API during the
live loop. It receives approved ``Signal`` objects, places bracket orders
(limit entry + stop-loss + take-profit), maintains an in-memory position
registry, reacts to fills in real time, and serialises the registry to a trade
log at shutdown.

This is the live-session equivalent of the legacy ``3_placed_orders.csv`` /
``track_orders.py`` flow, but fills arrive via event callbacks inside the same
session instead of a separate reconciliation process.
"""

import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path

import asyncio
import pandas as pd
from ib_async import IB, Stock, LimitOrder, StopOrder

from brotools.trade_signal import Signal

logger = logging.getLogger(__name__)

TRADES_FILE = Path("DATA/4_trades.csv")


@dataclass
class PositionState:
    """In-memory record of a single bracket position."""

    symbol: str
    quantity: int
    reason: str
    signal_time: str
    submitted_at: str

    entry_price: float
    stop_price: float
    target_price: float

    parent_id: int = 0
    sl_id: int = 0
    tp_id: int = 0

    parent_status: str = "PendingSubmit"
    sl_status: str = "PendingSubmit"
    tp_status: str = "PendingSubmit"

    entry_fill_price: float | None = None
    exit_fill_price: float | None = None
    realized_pnl: float | None = None
    closed: bool = False

    # Trade objects are kept for cancellation/management but not serialised.
    trades: dict = field(default_factory=dict, repr=False)


class OrderManager:
    def __init__(self, ib: IB, strategy) -> None:
        self.ib = ib
        self.strategy = strategy
        self.registry: dict[str, PositionState] = {}

    # ------------------------------------------------------------------
    def open_symbols(self) -> set[str]:
        """Symbols with a position that has not yet been closed."""
        return {s for s, p in self.registry.items() if not p.closed}

    # ------------------------------------------------------------------
    # Phase 5 — place a bracket order for an approved signal
    # ------------------------------------------------------------------
    async def place(self, signal: Signal) -> PositionState | None:
        contract = Stock(signal.symbol, "SMART", "USD")
        await self.ib.qualifyContractsAsync(contract)

        # Limit entry at the signal bar's close; bracketed stop + target.
        # transmit=False on parent + stop so TWS holds the group until the
        # take-profit (transmit=True) arrives, then transmits atomically.
        parent = LimitOrder("BUY", signal.quantity, signal.entry_price,
                            tif="GTC", transmit=False)
        stop = StopOrder("SELL", signal.quantity, signal.stop_price,
                        tif="GTC", transmit=False)
        target = LimitOrder("SELL", signal.quantity, signal.target_price,
                            tif="GTC", transmit=True)

        parent_trade = self.ib.placeOrder(contract, parent)
        await self._yield()                # TWS assigns parent orderId

        stop.parentId = parent.orderId
        target.parentId = parent.orderId
        sl_trade = self.ib.placeOrder(contract, stop)
        tp_trade = self.ib.placeOrder(contract, target)
        await self._yield()                # TWS acks children

        state = PositionState(
            symbol=signal.symbol,
            quantity=signal.quantity,
            reason=signal.reason,
            signal_time=str(signal.signal_time),
            submitted_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            entry_price=signal.entry_price,
            stop_price=signal.stop_price,
            target_price=signal.target_price,
            parent_id=parent.orderId,
            sl_id=stop.orderId,
            tp_id=target.orderId,
            parent_status=parent_trade.orderStatus.status,
            sl_status=sl_trade.orderStatus.status,
            tp_status=tp_trade.orderStatus.status,
            trades={"parent": parent_trade, "sl": sl_trade, "tp": tp_trade},
        )
        self.registry[signal.symbol] = state

        # Wire fill callbacks for real-time tracking.
        parent_trade.filledEvent += self._make_parent_handler(signal.symbol)
        sl_trade.filledEvent += self._make_exit_handler(signal.symbol, "stop")
        tp_trade.filledEvent += self._make_exit_handler(signal.symbol, "target")

        logger.info(
            "✅ %s bracket placed (entry %.2f / stop %.2f / target %.2f, parent %d)",
            signal.symbol, signal.entry_price, signal.stop_price,
            signal.target_price, parent.orderId,
        )
        return state

    # ------------------------------------------------------------------
    # Fill handlers
    # ------------------------------------------------------------------
    def _make_parent_handler(self, symbol: str):
        def handler(trade, fill):
            state = self.registry.get(symbol)
            if state is None:
                return
            state.parent_status = trade.orderStatus.status
            state.entry_fill_price = trade.orderStatus.avgFillPrice or state.entry_price
            logger.info("🟢 %s entry filled @ %.2f", symbol, state.entry_fill_price)
            self.strategy.on_fill(symbol, {"leg": "entry", "fill": fill})
        return handler

    def _make_exit_handler(self, symbol: str, leg: str):
        def handler(trade, fill):
            state = self.registry.get(symbol)
            if state is None or state.closed:
                return
            state.exit_fill_price = trade.orderStatus.avgFillPrice
            if leg == "stop":
                state.sl_status = trade.orderStatus.status
            else:
                state.tp_status = trade.orderStatus.status
            if state.entry_fill_price is not None and state.exit_fill_price is not None:
                state.realized_pnl = round(
                    (state.exit_fill_price - state.entry_fill_price) * state.quantity, 2
                )
            state.closed = True
            logger.info(
                "🔴 %s closed via %s @ %.2f (P&L %.2f)",
                symbol, leg, state.exit_fill_price or 0.0, state.realized_pnl or 0.0,
            )
            self.strategy.on_fill(symbol, {"leg": leg, "fill": fill})
        return handler

    # ------------------------------------------------------------------
    # Phase 7 — shutdown helpers
    # ------------------------------------------------------------------
    def cancel_unfilled(self) -> None:
        """Cancel parent orders that have not filled (children auto-cancel)."""
        for symbol, state in self.registry.items():
            if state.parent_status == "Filled":
                continue
            parent_trade = state.trades.get("parent")
            if parent_trade is not None:
                try:
                    self.ib.cancelOrder(parent_trade.order)
                    logger.info("🚫 Cancelled unfilled entry for %s.", symbol)
                except Exception as e:  # noqa: BLE001
                    logger.error("❌ Cancel failed for %s: %s", symbol, e)

    def save_trade_log(self, filepath: Path = TRADES_FILE) -> None:
        if not self.registry:
            logger.info("No positions to log.")
            return
        rows = []
        for state in self.registry.values():
            row = asdict(state)
            row.pop("trades", None)
            rows.append(row)
        write_header = not filepath.exists()
        pd.DataFrame(rows).to_csv(filepath, mode="a", header=write_header, index=False)
        logger.info("💾 Saved %d position(s) to %s", len(rows), filepath)

    # ------------------------------------------------------------------
    @staticmethod
    async def _yield() -> None:
        await asyncio.sleep(0)
