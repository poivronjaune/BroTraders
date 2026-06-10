"""
bot_session.py

BotSession — top-level orchestrator for the live, event-driven trading session.
It owns the single persistent IB connection and drives the seven phases:

  1. Startup      — load strategy, connect, wire components, idle to start time
  2. Scanner       — run the strategy's scanner, build the watch list
  3. Data init     — fetch warm history + subscribe to live bars
  4. Live loop     — react to confirmed bars until done / session end
  5. Orders        — handled by OrderManager throughout phase 4
  6. Risk          — handled by RiskManager throughout phase 4
  7. Shutdown      — cancel unfilled, (optionally) close, save log, disconnect

``run`` is the synchronous entry point exposed as the ``run_bot`` CLI command.
"""

import asyncio
import importlib
import logging
import os
from datetime import datetime, timedelta

from ib_async import IB

from brotools.config import STRATEGY_FILE
from brotools.log_config import configure_logging
from brotools.services import connect_with_retry, run_scanner_async
from brotools.data_manager import DataManager
from brotools.order_manager import OrderManager
from brotools.risk_manager import RiskManager
from brotools.strategy_runner import StrategyRunner

logger = logging.getLogger(__name__)


def _load_strategy_class():
    """Dynamically load the active strategy class from config.STRATEGY_FILE."""
    module_name = STRATEGY_FILE.replace(".py", "")
    try:
        strategy_module = importlib.import_module(f"brotools.strategies.{module_name}")
        return strategy_module.Strategy
    except (ModuleNotFoundError, AttributeError) as e:
        raise RuntimeError(f"❌ Could not load strategy '{module_name}': {e}")


def _create_folders() -> None:
    os.makedirs("DATA", exist_ok=True)


def _parse_hhmm_today(hhmm: str) -> datetime:
    """Return today's datetime for an 'HH:MM' string (local clock)."""
    hour, minute = (int(x) for x in hhmm.split(":"))
    now = datetime.now()
    return now.replace(hour=hour, minute=minute, second=0, microsecond=0)


class BotSession:
    def __init__(self, ib: IB, strategy) -> None:
        self.ib = ib
        self.strategy = strategy
        self.order_manager = OrderManager(ib, strategy)
        self.risk_manager = RiskManager(strategy)
        self.data_manager = DataManager(ib, strategy)
        self.runner = StrategyRunner(self.strategy, self.order_manager, self.risk_manager)
        self.data_manager.set_bar_callback(self.runner.on_bar_ready)

    # ------------------------------------------------------------------
    # Phase 1 — idle until the strategy's session start time
    # ------------------------------------------------------------------
    async def _wait_until(self, hhmm: str) -> None:
        target = _parse_hhmm_today(hhmm)
        while datetime.now() < target:
            remaining = (target - datetime.now()).total_seconds()
            logger.info("⏳ Waiting %.0fs until %s ...", max(remaining, 0), hhmm)
            await asyncio.sleep(min(remaining, 30))

    # ------------------------------------------------------------------
    # Phase 2 — scanner
    # ------------------------------------------------------------------
    async def _run_scanner(self) -> list[str]:
        logger.info("🔍 Running scanner for %s ...", self.strategy.name)
        scan_df = await run_scanner_async(self.ib, self.strategy)

        if scan_df is not None and not scan_df.empty:
            scan_df = scan_df.copy()
            scan_df["strategy"] = self.strategy.name
            scan_df.to_csv("DATA/1_scan_results.csv", index=False)
            logger.info("✅ Scan returned %d prospects.", len(scan_df))
        else:
            logger.warning("⚠️  Scanner returned no results.")

        symbols = self.strategy.on_scan_results(scan_df)
        logger.info("👀 Watch list (%d): %s", len(symbols), symbols)
        return symbols

    # ------------------------------------------------------------------
    # Phase 4 — live loop
    # ------------------------------------------------------------------
    async def _live_loop(self) -> None:
        logger.info("🟢 Entering live trading loop (until %s).", self.strategy.session_end_time)
        while True:
            if self.risk_manager.kill_switch_active():
                logger.warning("🛑 Kill switch detected — ending session.")
                break
            if self.strategy.is_session_done():
                logger.info("🏁 Strategy reports session done — ending loop.")
                break
            if datetime.now().strftime("%H:%M") >= self.strategy.session_end_time:
                logger.info("⏰ Session end time reached — ending loop.")
                break
            # Yield to the event loop so ib_async can process incoming bars/fills.
            await asyncio.sleep(1)

    # ------------------------------------------------------------------
    # Phase 7 — shutdown
    # ------------------------------------------------------------------
    async def _shutdown(self) -> None:
        logger.info("🧹 Shutting down session ...")
        self.order_manager.cancel_unfilled()

        if getattr(self.strategy, "close_on_session_end", False):
            await self._close_open_positions()

        self.order_manager.save_trade_log()
        await asyncio.sleep(0.5)  # let cancellations propagate
        self.ib.disconnect()
        logger.info("✅ Session ended and disconnected from TWS.")

    async def _close_open_positions(self) -> None:
        from ib_async import Stock, MarketOrder
        for symbol in self.order_manager.open_symbols():
            state = self.order_manager.registry[symbol]
            if state.parent_status != "Filled":
                continue  # never entered; cancel_unfilled handles it
            try:
                contract = Stock(symbol, "SMART", "USD")
                await self.ib.qualifyContractsAsync(contract)
                self.ib.placeOrder(contract, MarketOrder("SELL", state.quantity))
                logger.info("📤 Market-closing %s (%d shares).", symbol, state.quantity)
            except Exception as e:  # noqa: BLE001
                logger.error("❌ Failed to close %s: %s", symbol, e)

    # ------------------------------------------------------------------
    async def run(self) -> None:
        # Phase 1
        await self._wait_until(self.strategy.session_start_time)
        # Phase 2
        symbols = await self._run_scanner()
        if not symbols:
            logger.warning("⚠️  Empty watch list — nothing to trade. Shutting down.")
            await self._shutdown()
            return
        # Phase 3
        await self.data_manager.initialize(symbols)
        # Phase 4 (+ 5 + 6 via events)
        await self._live_loop()
        # Phase 7
        await self._shutdown()


# ---------------------------------------------------------------------------
# Entry point — exposed as the `run_bot` CLI command
# ---------------------------------------------------------------------------

async def _run_async() -> None:
    Strategy = _load_strategy_class()
    ib = IB()
    with Strategy() as strategy:
        try:
            await connect_with_retry(ib)
            session = BotSession(ib, strategy)
            await session.run()
        finally:
            if ib.isConnected():
                ib.disconnect()


def run() -> None:
    configure_logging()
    _create_folders()
    try:
        asyncio.run(_run_async())
    except KeyboardInterrupt:
        logger.warning("⚠️  Interrupted by user — exiting.")
    except Exception as e:  # noqa: BLE001
        logger.error("❌ Bot session failed: %s", e, exc_info=True)
