"""SQLite-backed, lifecycle-based trading log."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class TradingLog:
    """Persist trades and their related IBKR orders in SQLite."""

    def __init__(self, db_path: str | Path = Path("DB") / "trades.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.db_path)
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._create_schema()

    def _create_schema(self) -> None:
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS trades (
                trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_name TEXT NOT NULL,
                symbol TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                signal_time TEXT NOT NULL,
                status TEXT NOT NULL,
                entry_time TEXT,
                entry_price REAL,
                exit_time TEXT,
                exit_price REAL,
                exit_reason TEXT,
                gross_pnl REAL,
                commissions REAL,
                net_pnl REAL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS orders (
                order_id INTEGER PRIMARY KEY,
                trade_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                order_type TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                price REAL,
                status TEXT NOT NULL,
                filled_quantity INTEGER,
                average_fill_price REAL,
                update_time TEXT,
                FOREIGN KEY (trade_id) REFERENCES trades(trade_id)
            );
            """
        )
        self._connection.commit()

    @staticmethod
    def _timestamp(value: datetime | str | None = None) -> str:
        if value is None:
            value = datetime.now(timezone.utc)
        if isinstance(value, datetime):
            return value.isoformat()
        return value

    def create_trade(
        self,
        strategy_name: str,
        symbol: str,
        quantity: int,
        signal_time: datetime | str,
        status: str = "PLACED",
    ) -> int:
        """Create a trade row and return its generated identifier."""
        now = self._timestamp()
        cursor = self._connection.execute(
            """
            INSERT INTO trades (
                strategy_name, symbol, quantity, signal_time, status,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                strategy_name,
                symbol,
                quantity,
                self._timestamp(signal_time),
                status,
                now,
                now,
            ),
        )
        return int(cursor.lastrowid)

    def add_order(
        self,
        trade_id: int,
        order_id: int,
        role: str,
        order_type: str,
        quantity: int,
        price: float | None,
        status: str,
    ) -> int:
        """Record an IBKR order linked to an existing trade."""
        self._connection.execute(
            """
            INSERT INTO orders (
                order_id, trade_id, role, order_type, quantity, price, status,
                update_time
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                order_id,
                trade_id,
                role,
                order_type,
                quantity,
                price,
                status,
                self._timestamp(),
            ),
        )
        return order_id

    def update_trade(
        self,
        trade_id: int,
        status: str,
        entry_time: datetime | str | None = None,
        entry_price: float | None = None,
        exit_time: datetime | str | None = None,
        exit_price: float | None = None,
        exit_reason: str | None = None,
        gross_pnl: float | None = None,
        commissions: float | None = None,
        net_pnl: float | None = None,
    ) -> None:
        """Update the supplied lifecycle fields for an existing trade."""
        fields: dict[str, Any] = {"status": status, "updated_at": self._timestamp()}
        optional_values = {
            "entry_time": entry_time,
            "entry_price": entry_price,
            "exit_time": exit_time,
            "exit_price": exit_price,
            "exit_reason": exit_reason,
            "gross_pnl": gross_pnl,
            "commissions": commissions,
            "net_pnl": net_pnl,
        }
        fields.update(
            {
                name: self._timestamp(value) if name.endswith("_time") else value
                for name, value in optional_values.items()
                if value is not None
            }
        )
        assignments = ", ".join(f"{name} = ?" for name in fields)
        cursor = self._connection.execute(
            f"UPDATE trades SET {assignments} WHERE trade_id = ?",
            (*fields.values(), trade_id),
        )
        if cursor.rowcount == 0:
            raise ValueError(f"Trade {trade_id} does not exist")

    def update_order(
        self,
        order_id: int,
        status: str,
        filled_quantity: int | None = None,
        average_fill_price: float | None = None,
        update_time: datetime | str | None = None,
    ) -> None:
        """Update the status and fill details for an existing order."""
        fields: dict[str, Any] = {
            "status": status,
            "update_time": self._timestamp(update_time),
        }
        if filled_quantity is not None:
            fields["filled_quantity"] = filled_quantity
        if average_fill_price is not None:
            fields["average_fill_price"] = average_fill_price
        assignments = ", ".join(f"{name} = ?" for name in fields)
        cursor = self._connection.execute(
            f"UPDATE orders SET {assignments} WHERE order_id = ?",
            (*fields.values(), order_id),
        )
        if cursor.rowcount == 0:
            raise ValueError(f"Order {order_id} does not exist")

    def flush(self) -> None:
        """Commit all pending trading-log changes."""
        self._connection.commit()

    def close(self) -> None:
        """Commit pending changes and close the database connection."""
        self.flush()
        self._connection.close()

    def __enter__(self) -> TradingLog:
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        if exc_type is None:
            self.close()
        else:
            self._connection.close()
