"""
track_orders.py

Connects to IBKR TWS, reconciles the status of all open orders in
3_placed_orders.csv against live execution reports, updates statuses
in-place, and writes completed trades to 4_trades.csv.

A trade is considered complete when:
  - The parent (buy) order is Filled
  - Exactly one of its children (SL or TP) is Filled (the other is Cancelled)

Run this script independently from the order-placement script.
"""

import asyncio
from datetime import datetime
from pathlib import Path

import pandas as pd
from ib_async import IB, ExecutionFilter

from brotools.config import IBKR_HOST, IBKR_PORT, IBKR_CLIENT_ID

# ---------------------------------------------------------------------------
# File paths
# ---------------------------------------------------------------------------
PLACED_ORDERS_FILE = Path("DATA/3_placed_orders.csv")
TRADES_FILE        = Path("DATA/4_trades.csv")

# ---------------------------------------------------------------------------
# Terminal states — rows in these states are historical, skip re-querying
# ---------------------------------------------------------------------------
TERMINAL_STATES = {"Filled", "Cancelled", "Inactive"}

# ---------------------------------------------------------------------------
# Columns added during tracking (may not exist in older CSV versions)
# ---------------------------------------------------------------------------
TIMESTAMP_COLUMNS = [
    "parent_filled_at",
    "sl_filled_at",
    "tp_filled_at",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_placed_orders(filepath: Path) -> pd.DataFrame:
    """
    Load 3_placed_orders.csv, adding any missing columns gracefully.

    Handles legacy files that may be missing:
      - submitted_at  (older files used placed_at or had no timestamp at all)
      - parent_filled_at, sl_filled_at, tp_filled_at
    """
    df = pd.read_csv(filepath)

    # Handle legacy column name rename
    if "placed_at" in df.columns and "submitted_at" not in df.columns:
        df.rename(columns={"placed_at": "submitted_at"}, inplace=True)

    # If still missing (very old file with no timestamp), default to today at
    # midnight so the ExecutionFilter still returns today's executions.
    # Log a warning so the user knows the fallback was applied.
    if "submitted_at" not in df.columns:
        fallback = datetime.now().strftime("%Y-%m-%d 00:00:00")
        df["submitted_at"] = fallback
        print(f"⚠️  No submitted_at column found — defaulting to {fallback} "
              f"for all rows. Consider adding submitted_at to your CSV.")

    # Add missing timestamp columns — explicitly typed as object so string
    # timestamps can be written later without pandas dtype conflicts.
    # Columns loaded from CSV with all-NaN values are inferred as float64
    # by pandas, which rejects string assignment at df.at[] time.
    for col in TIMESTAMP_COLUMNS:
        if col not in df.columns:
            df[col] = pd.Series(dtype="object")
        else:
            df[col] = df[col].astype("object")

    return df


def is_trade_historical(row: pd.Series) -> bool:
    """
    A row is historical (fully resolved) when the parent is Filled AND
    exactly one child is Filled and the other is Cancelled.
    """
    parent_done = row["parent_status"] == "Filled"
    sl_terminal = row["sl_status"] in TERMINAL_STATES
    tp_terminal = row["tp_status"] in TERMINAL_STATES
    return parent_done and sl_terminal and tp_terminal


def get_active_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Return rows that still need tracking (not yet fully resolved)."""
    return df[~df.apply(is_trade_historical, axis=1)]


def oldest_submitted_at(df_active: pd.DataFrame) -> str:
    """
    Return the oldest submitted_at among active rows, formatted for
    IBKR ExecutionFilter (YYYYMMDD HH:MM:SS).
    """
    oldest = pd.to_datetime(df_active["submitted_at"]).min()
    return oldest.strftime("%Y%m%d %H:%M:%S")


def build_order_id_index(df: pd.DataFrame) -> dict:
    """
    Build a lookup: orderId (int) → (dataframe index, role)
    role is one of: 'parent', 'sl', 'tp'
    """
    index = {}
    for i, row in df.iterrows():
        index[int(row["parent_order_id"])] = (i, "parent")
        index[int(row["sl_order_id"])]     = (i, "sl")
        index[int(row["tp_order_id"])]     = (i, "tp")
    return index


def fmt_dt(dt) -> str | None:
    """Format a datetime to string, or return None if not available."""
    if dt is None:
        return None
    if isinstance(dt, str):
        return dt
    return dt.strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------------
# Core async logic
# ---------------------------------------------------------------------------

async def fetch_executions(ib: IB, time_filter: str) -> list:
    """Request execution reports from TWS from time_filter onwards."""
    exec_filter = ExecutionFilter(time=time_filter)
    executions  = await ib.reqExecutionsAsync(exec_filter)
    return executions


def apply_executions_to_df(
    df: pd.DataFrame,
    executions: list,
    order_id_index: dict,
) -> pd.DataFrame:
    """
    Walk through execution reports and update df rows with:
      - current status
      - filled_at timestamps
      - fill prices and quantities (stored temporarily for trade log)
    """
    # Attach fill data to the dataframe temporarily for trade-log building
    for col in ["parent_fill_price", "parent_fill_qty", "parent_fill_time",
                "exit_fill_price",   "exit_fill_qty",   "exit_fill_time",
                "exit_role",         "parent_commission","exit_commission"]:
        if col not in df.columns:
            df[col] = None

    for exec_obj in executions:
        order_id   = exec_obj.execution.orderId
        fill_price = exec_obj.execution.avgPrice
        fill_qty   = exec_obj.execution.cumQty
        fill_time  = exec_obj.execution.time  # string from IBKR e.g. "20250602 09:31:05"

        # Parse commission — may arrive as 0 or be missing
        commission = None
        if exec_obj.commissionReport is not None:
            raw = exec_obj.commissionReport.commission
            commission = raw if (raw is not None and raw > 0) else None

        if order_id not in order_id_index:
            continue  # execution belongs to an order we didn't place

        idx, role = order_id_index[order_id]

        # Parse fill time to a standard string
        try:
            parsed_time = datetime.strptime(fill_time, "%Y%m%d %H:%M:%S")
            fill_time_str = parsed_time.strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            fill_time_str = fmt_dt(fill_time)

        if role == "parent":
            df.at[idx, "parent_status"]      = "Filled"
            df.at[idx, "parent_filled_at"]   = fill_time_str
            df.at[idx, "parent_fill_price"]  = fill_price
            df.at[idx, "parent_fill_qty"]    = fill_qty
            df.at[idx, "parent_fill_time"]   = fill_time_str
            df.at[idx, "parent_commission"]  = commission

        elif role == "sl":
            df.at[idx, "sl_status"]        = "Filled"
            df.at[idx, "sl_filled_at"]     = fill_time_str
            df.at[idx, "exit_fill_price"]  = fill_price
            df.at[idx, "exit_fill_qty"]    = fill_qty
            df.at[idx, "exit_fill_time"]   = fill_time_str
            df.at[idx, "exit_role"]        = "sl"
            df.at[idx, "exit_commission"]  = commission

        elif role == "tp":
            df.at[idx, "tp_status"]        = "Filled"
            df.at[idx, "tp_filled_at"]     = fill_time_str
            df.at[idx, "exit_fill_price"]  = fill_price
            df.at[idx, "exit_fill_qty"]    = fill_qty
            df.at[idx, "exit_fill_time"]   = fill_time_str
            df.at[idx, "exit_role"]        = "tp"
            df.at[idx, "exit_commission"]  = commission

    # For cancelled children: mark status and mirror the sibling's filled_at
    # IBKR does not generate an execution report for a cancelled order,
    # so we infer cancellation from the bracket logic (one child filled → other cancelled)
    for i, row in df.iterrows():
        if row["parent_status"] != "Filled":
            continue

        sl_filled = row["sl_status"] == "Filled"
        tp_filled = row["tp_status"] == "Filled"

        if sl_filled and row["tp_status"] not in TERMINAL_STATES:
            df.at[i, "tp_status"]    = "Cancelled"
            df.at[i, "tp_filled_at"] = row["sl_filled_at"]  # mirror sibling time

        if tp_filled and row["sl_status"] not in TERMINAL_STATES:
            df.at[i, "sl_status"]    = "Cancelled"
            df.at[i, "sl_filled_at"] = row["tp_filled_at"]  # mirror sibling time

    return df


def save_placed_orders(df: pd.DataFrame, filepath: Path) -> None:
    """
    Save only the columns that belong in 3_placed_orders.csv.
    Temporary trade-computation columns are excluded.
    """
    output_cols = [
        "symbol", "submitted_at",
        "parent_order_id", "parent_status", "parent_filled_at",
        "sl_order_id",     "sl_status",     "sl_filled_at",
        "tp_order_id",     "tp_status",     "tp_filled_at",
    ]
    df[output_cols].to_csv(filepath, index=False)
    print(f"💾 Updated {filepath} ({len(df)} rows)")


def build_trade_log(df: pd.DataFrame, existing_trades: pd.DataFrame) -> pd.DataFrame:
    """
    From fully resolved rows in df, build trade log entries.
    Skips any parent_order_id already present in existing_trades.
    """
    existing_ids = set()
    if not existing_trades.empty and "parent_order_id" in existing_trades.columns:
        existing_ids = set(existing_trades["parent_order_id"].astype(int).tolist())

    new_trades = []

    for _, row in df.iterrows():
        if not is_trade_historical(row):
            continue
        if int(row["parent_order_id"]) in existing_ids:
            continue  # already recorded in a previous run

        entry_price    = row.get("parent_fill_price")
        exit_price     = row.get("exit_fill_price")
        quantity       = row.get("parent_fill_qty")
        parent_comm    = row.get("parent_commission")
        exit_comm      = row.get("exit_commission")
        exit_role      = row.get("exit_role")  # 'sl' or 'tp'

        # Raw P&L
        if entry_price is not None and exit_price is not None and quantity is not None:
            raw_pnl = (float(exit_price) - float(entry_price)) * float(quantity)
        else:
            raw_pnl = None

        # Total commission — handle missing values gracefully
        if parent_comm is not None and exit_comm is not None:
            total_commission = float(parent_comm) + float(exit_comm)
        elif parent_comm is not None:
            total_commission = float(parent_comm)
        elif exit_comm is not None:
            total_commission = float(exit_comm)
        else:
            total_commission = None  # commission data unavailable

        # Net P&L
        if raw_pnl is not None and total_commission is not None:
            net_pnl = raw_pnl - total_commission
        else:
            net_pnl = None

        new_trades.append({
            "symbol":           row["symbol"],
            "parent_order_id":  int(row["parent_order_id"]),
            "sl_order_id":      int(row["sl_order_id"]),
            "tp_order_id":      int(row["tp_order_id"]),
            "submitted_at":     row["submitted_at"],
            "parent_filled_at": row.get("parent_filled_at"),
            "sl_filled_at":     row.get("sl_filled_at"),
            "tp_filled_at":     row.get("tp_filled_at"),
            "exit_via":         exit_role,           # 'sl' or 'tp'
            "entry_price":      entry_price,
            "exit_price":       exit_price,
            "quantity":         quantity,
            "raw_pnl":          round(raw_pnl, 4)          if raw_pnl          is not None else None,
            "parent_commission":round(float(parent_comm), 4) if parent_comm    is not None else None,
            "exit_commission":  round(float(exit_comm), 4)   if exit_comm      is not None else None,
            "total_commission": round(total_commission, 4)   if total_commission is not None else None,
            "net_pnl":          round(net_pnl, 4)            if net_pnl        is not None else None,
        })

    return pd.DataFrame(new_trades)


def save_trade_log(new_trades: pd.DataFrame, filepath: Path) -> None:
    """Append new trades to 4_trades.csv, creating the file if needed."""
    if new_trades.empty:
        print("No new completed trades to write.")
        return

    write_header = not filepath.exists()
    new_trades.to_csv(filepath, mode="a", header=write_header, index=False)
    print(f"📈 Wrote {len(new_trades)} new trade(s) to {filepath}")


# ---------------------------------------------------------------------------
# Cancellation tracking — separate workflow, runs after track_orders_async
# ---------------------------------------------------------------------------

def apply_cancellations_to_df(
    df: pd.DataFrame,
    open_order_ids: set,
) -> tuple[pd.DataFrame, int]:
    """
    For each active row whose parent order ID is NOT in open_order_ids,
    mark the parent and both children as Cancelled.

    The absence from open orders means TWS no longer considers the order
    live — it was cancelled either via API or manually in TWS.

    Returns:
        (updated df, count of rows newly cancelled)
    """
    cancelled_count = 0
    cancelled_at    = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for i, row in df.iterrows():
        if is_trade_historical(row):
            continue  # already fully resolved — skip

        if int(row["parent_order_id"]) in open_order_ids:
            continue  # still live in TWS — skip

        # Not in open orders and not historical → was cancelled
        df.at[i, "parent_status"]    = "Cancelled"
        df.at[i, "parent_filled_at"] = cancelled_at
        df.at[i, "sl_status"]        = "Cancelled"
        df.at[i, "sl_filled_at"]     = cancelled_at
        df.at[i, "tp_status"]        = "Cancelled"
        df.at[i, "tp_filled_at"]     = cancelled_at

        print(f"🚫 {row['symbol']} marked Cancelled "
              f"(Parent ID: {int(row['parent_order_id'])})")
        cancelled_count += 1

    return df, cancelled_count


async def track_cancellations_async() -> None:
    """
    Second-pass workflow: detect orders that were cancelled in TWS
    (manually or via API) and update 3_placed_orders.csv accordingly.

    Strategy:
      - Fetch all currently open orders from TWS
      - Any row in our CSV that is still active but whose parent order ID
        is absent from the open orders list was cancelled
      - Mark parent + both children as Cancelled and save

    Does NOT write to 4_trades.csv — cancelled parents have no P&L to record.

    Note: reqAllOpenOrdersAsync returns orders from all client IDs, so
    manually cancelled orders in TWS are included regardless of how they
    were cancelled.
    """
    # 1. Reload placed orders fresh — track_orders_async may have updated the file
    if not PLACED_ORDERS_FILE.exists():
        print(f"❌ {PLACED_ORDERS_FILE} not found.")
        return

    df       = load_placed_orders(PLACED_ORDERS_FILE)
    df_active = get_active_rows(df)

    if df_active.empty:
        print("✅ No active orders remaining — cancellation check skipped.")
        return

    print(f"🔍 Checking cancellations for {len(df_active)} active order(s)...")

    # 2. Fetch all currently open orders from TWS
    ib = IB()
    try:
        await ib.connectAsync(IBKR_HOST, IBKR_PORT, clientId=IBKR_CLIENT_ID)
        open_trades = await ib.reqAllOpenOrdersAsync()
        print(f"📡 Received {len(open_trades)} open order(s) from TWS.")
    finally:
        ib.disconnect()

    # 3. Build set of all order IDs still live in TWS
    # reqAllOpenOrdersAsync returns Trade objects — each has an order with orderId
    open_order_ids = {t.order.orderId for t in open_trades}

    # 4. Mark cancelled rows in the dataframe
    df, cancelled_count = apply_cancellations_to_df(df, open_order_ids)

    if cancelled_count == 0:
        print("✅ No cancellations detected.")
        return

    # 5. Save updated 3_placed_orders.csv
    save_placed_orders(df, PLACED_ORDERS_FILE)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

async def track_orders_async() -> None:
    """Main async entry point."""

    # 1. Load placed orders
    if not PLACED_ORDERS_FILE.exists():
        print(f"❌ {PLACED_ORDERS_FILE} not found.")
        return

    df = load_placed_orders(PLACED_ORDERS_FILE)

    # 2. Identify rows that still need tracking
    df_active = get_active_rows(df)

    if df_active.empty:
        print("✅ All orders are already in a terminal state. Nothing to track.")
        return

    print(f"🔍 {len(df_active)} active order(s) to reconcile "
          f"({len(df) - len(df_active)} historical).")

    # 3. Determine time filter from oldest active submitted_at
    time_filter = oldest_submitted_at(df_active)
    print(f"⏱  Fetching executions from {time_filter} onwards...")

    # 4. Build order ID → row index lookup (active rows only)
    order_id_index = build_order_id_index(df_active)

    # 5. Connect to IBKR and fetch executions
    ib = IB()
    try:
        await ib.connectAsync(IBKR_HOST, IBKR_PORT, clientId=IBKR_CLIENT_ID)
        executions = await fetch_executions(ib, time_filter)
        print(f"📡 Received {len(executions)} execution report(s) from TWS.")
    finally:
        ib.disconnect()

    # 6. Apply executions to dataframe
    df = apply_executions_to_df(df, executions, order_id_index)

    # 7. Save updated 3_placed_orders.csv (changed rows only, full rewrite of file)
    save_placed_orders(df, PLACED_ORDERS_FILE)

    # 8. Load existing trade log (if any) to avoid duplicates
    if TRADES_FILE.exists():
        existing_trades = pd.read_csv(TRADES_FILE)
    else:
        existing_trades = pd.DataFrame()

    # 9. Build and save new trade log entries
    new_trades = build_trade_log(df, existing_trades)
    save_trade_log(new_trades, TRADES_FILE)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def _main():                                      # <-- change: added to run both workflows
    await track_orders_async()
    await track_cancellations_async()


def track_orders():
    """Synchronous wrapper — runs fill tracking then cancellation tracking."""
    asyncio.run(_main())                                # <-- change: was asyncio.run(track_orders_async())


if __name__ == "__main__":
    asyncio.run(_main())                                # <-- change: was asyncio.run(track_orders_async())
