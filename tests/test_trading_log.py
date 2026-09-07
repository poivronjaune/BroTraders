import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from brotoolsv2.trading_log import TradingLog


@pytest.fixture
def tmp_path(request):
    """Provide a per-test database directory retained for inspection."""
    test_path = (
        Path(__file__).resolve().parents[1]
        / "TESTS_TMP_FILES"
        / request.node.name
    )
    shutil.rmtree(test_path, ignore_errors=True)
    test_path.mkdir(parents=True)
    return test_path


@pytest.fixture
def trading_log(tmp_path):
    log = TradingLog(tmp_path / "trades.db")
    yield log
    try:
        log.close()
    except sqlite3.ProgrammingError:
        pass


def create_placed_trade(log: TradingLog, symbol: str = "AAPL") -> int:
    return log.create_trade(
        strategy_name="gap_rise",
        symbol=symbol,
        quantity=100,
        signal_time=datetime(2026, 9, 6, 13, 30, tzinfo=timezone.utc),
    )


def test_database_initialization_creates_database_and_tables(tmp_path):
    database_path = tmp_path / "nested" / "trades.db"

    log = TradingLog(database_path)
    try:
        table_names = {
            row[0]
            for row in log._connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    finally:
        log.close()

    assert database_path.exists()
    assert {"trades", "orders"} <= table_names


def test_create_placed_trade_stores_initial_values(trading_log):
    trade_id = create_placed_trade(trading_log)

    trade = trading_log._connection.execute(
        "SELECT strategy_name, symbol, quantity, signal_time, status "
        "FROM trades WHERE trade_id = ?",
        (trade_id,),
    ).fetchone()

    assert trade == (
        "gap_rise",
        "AAPL",
        100,
        "2026-09-06T13:30:00+00:00",
        "PLACED",
    )


def test_add_bracket_orders_links_each_order_to_trade(trading_log):
    trade_id = create_placed_trade(trading_log)
    orders = [
        (101, "ENTRY", "MKT", 100, None, "SUBMITTED"),
        (102, "STOP_LOSS", "STP", 100, 95.0, "SUBMITTED"),
        (103, "TAKE_PROFIT", "LMT", 100, 110.0, "SUBMITTED"),
    ]

    for order in orders:
        assert trading_log.add_order(trade_id, *order) == order[0]

    stored_orders = trading_log._connection.execute(
        "SELECT order_id, trade_id, role, order_type, quantity, price, status "
        "FROM orders ORDER BY order_id"
    ).fetchall()

    assert stored_orders == [(order[0], trade_id, *order[1:]) for order in orders]


def test_update_order_status_stores_fill_details(trading_log):
    trade_id = create_placed_trade(trading_log)
    trading_log.add_order(trade_id, 101, "ENTRY", "MKT", 100, None, "SUBMITTED")

    trading_log.update_order(
        101,
        "FILLED",
        filled_quantity=100,
        average_fill_price=100.25,
        update_time="2026-09-06T13:31:00+00:00",
    )

    order = trading_log._connection.execute(
        "SELECT status, filled_quantity, average_fill_price, update_time "
        "FROM orders WHERE order_id = 101"
    ).fetchone()

    assert order == ("FILLED", 100, 100.25, "2026-09-06T13:31:00+00:00")


def test_trade_filled_lifecycle_stores_entry_details(trading_log):
    trade_id = create_placed_trade(trading_log)

    trading_log.update_trade(
        trade_id,
        "FILLED",
        entry_time=datetime(2026, 9, 6, 13, 31, tzinfo=timezone.utc),
        entry_price=100.25,
    )

    trade = trading_log._connection.execute(
        "SELECT status, entry_time, entry_price FROM trades WHERE trade_id = ?",
        (trade_id,),
    ).fetchone()

    assert trade == ("FILLED", "2026-09-06T13:31:00+00:00", 100.25)


def test_trade_closed_lifecycle_stores_exit_and_pnl_details(trading_log):
    trade_id = create_placed_trade(trading_log)

    trading_log.update_trade(
        trade_id,
        "CLOSED",
        entry_time="2026-09-06T13:31:00+00:00",
        entry_price=100.25,
        exit_time="2026-09-06T13:35:00+00:00",
        exit_price=110.25,
        exit_reason="TAKE_PROFIT",
        gross_pnl=1000.0,
        commissions=2.5,
        net_pnl=997.5,
    )

    trade = trading_log._connection.execute(
        "SELECT status, entry_time, entry_price, exit_time, exit_price, "
        "exit_reason, gross_pnl, commissions, net_pnl FROM trades WHERE trade_id = ?",
        (trade_id,),
    ).fetchone()

    assert trade == (
        "CLOSED",
        "2026-09-06T13:31:00+00:00",
        100.25,
        "2026-09-06T13:35:00+00:00",
        110.25,
        "TAKE_PROFIT",
        1000.0,
        2.5,
        997.5,
    )


def test_trade_cancellation_keeps_unfilled_trade(trading_log):
    trade_id = create_placed_trade(trading_log)

    trading_log.update_trade(trade_id, "CANCELLED", exit_reason="SIGNAL_EXPIRED")

    trade = trading_log._connection.execute(
        "SELECT status, exit_reason FROM trades WHERE trade_id = ?",
        (trade_id,),
    ).fetchone()
    assert trade == ("CANCELLED", "SIGNAL_EXPIRED")


def test_flush_persists_data_for_reopened_database(tmp_path):
    database_path = tmp_path / "trades.db"
    log = TradingLog(database_path)
    trade_id = create_placed_trade(log)
    log.flush()
    log.close()

    reopened_log = TradingLog(database_path)
    try:
        assert reopened_log._connection.execute(
            "SELECT status FROM trades WHERE trade_id = ?", (trade_id,)
        ).fetchone() == ("PLACED",)
    finally:
        reopened_log.close()


def test_close_commits_pending_changes_and_rejects_later_writes(tmp_path):
    log = TradingLog(tmp_path / "trades.db")
    trade_id = create_placed_trade(log)
    log.close()

    reopened_log = TradingLog(tmp_path / "trades.db")
    try:
        assert reopened_log._connection.execute(
            "SELECT status FROM trades WHERE trade_id = ?", (trade_id,)
        ).fetchone() == ("PLACED",)
    finally:
        reopened_log.close()

    with pytest.raises(sqlite3.ProgrammingError):
        log.create_trade("gap_rise", "MSFT", 50, "2026-09-06T13:30:00+00:00")


def test_multiple_trades_remain_isolated_when_one_is_updated(trading_log):
    first_trade = create_placed_trade(trading_log, "AAPL")
    second_trade = create_placed_trade(trading_log, "MSFT")

    trading_log.update_trade(first_trade, "CLOSED", exit_price=110.0, net_pnl=975.0)

    trades = trading_log._connection.execute(
        "SELECT trade_id, symbol, status, exit_price, net_pnl "
        "FROM trades ORDER BY trade_id"
    ).fetchall()

    assert trades == [
        (first_trade, "AAPL", "CLOSED", 110.0, 975.0),
        (second_trade, "MSFT", "PLACED", None, None),
    ]


def test_missing_records_are_rejected_and_orders_require_a_trade(trading_log):
    with pytest.raises(ValueError, match="Trade 999 does not exist"):
        trading_log.update_trade(999, "CLOSED")

    with pytest.raises(ValueError, match="Order 999 does not exist"):
        trading_log.update_order(999, "FILLED")

    with pytest.raises(sqlite3.IntegrityError):
        trading_log.add_order(999, 1001, "ENTRY", "MKT", 10, None, "SUBMITTED")
