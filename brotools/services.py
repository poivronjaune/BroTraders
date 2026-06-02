"""
services.py

Core IBKR service functions for the BroTraders system.

Provides three main workflows:
  - get_report_async()     : Run a scanner and return results as a DataFrame
  - save_data_async()      : Fetch and save historical 1-min OHLCV bars per ticker
  - place_orders_async()   : Load buy signals, build bracket orders, and submit to TWS

Sync helpers (create_bracket_order, build_buy_orders) perform all order
construction without touching the IB connection, keeping async surface minimal.
"""

import asyncio
from datetime import datetime
from pathlib import Path

import pandas as pd
from ib_async import IB, Stock, util, MarketOrder, LimitOrder, StopOrder

from brotools.config import IBKR_HOST, IBKR_PORT, IBKR_CLIENT_ID
from brotools.strategies.gap_rise import Strategy

# ---------------------------------------------------------------------------
# File paths
# ---------------------------------------------------------------------------
BUY_SIGNALS_FILE   = Path("DATA/2_buy_signals.csv")
PLACED_ORDERS_FILE = Path("DATA/3_placed_orders.csv")
HISTORICAL_DATA_DIR = Path("DATA")

# ---------------------------------------------------------------------------
# Order parameters
# ---------------------------------------------------------------------------
DEFAULT_QUANTITY      = 1
STOP_LOSS_PCT         = 0.98   # 2% below estimated buy price
TAKE_PROFIT_PCT       = 1.05   # 5% above estimated buy price

# ---------------------------------------------------------------------------
# Order status — stable states to wait for before saving placed orders
# ---------------------------------------------------------------------------
SUBMITTED_STATES = {"PreSubmitted", "Submitted", "Filled"}

# ---------------------------------------------------------------------------
# Columns written to 3_placed_orders.csv
# ---------------------------------------------------------------------------
PLACED_ORDERS_COLUMNS = [
    "symbol",          "submitted_at",
    "parent_order_id", "parent_status", "parent_filled_at",
    "sl_order_id",     "sl_status",     "sl_filled_at",
    "tp_order_id",     "tp_status",     "tp_filled_at",
]


# ---------------------------------------------------------------------------
# Helpers — sync, no IB connection
# ---------------------------------------------------------------------------

def load_buy_signals(filepath: Path = BUY_SIGNALS_FILE) -> pd.DataFrame:
    """
    Load and filter buy signals from CSV.
    Returns only rows where buy_signal is True.
    """
    df = pd.read_csv(filepath, index_col="rank")
    return df[df["buy_signal"] == True]


def create_bracket_order(
    qte: int = DEFAULT_QUANTITY,
    estimated_buy_price: float = 100.0,
) -> tuple:
    """
    Build a bracket order (parent + stop loss + take profit).

    Returns:
        (parent, stop_loss, take_profit) — ib_async order objects.

    Note: transmit=False on parent and SL so TWS holds all three until
    the TP (transmit=True) is placed, then transmits the group atomically.
    """
    parent = MarketOrder("BUY", qte, tif="GTC", transmit=False)

    stop_price = round(estimated_buy_price * STOP_LOSS_PCT, 2)
    stop_loss  = StopOrder("SELL", qte, stop_price, tif="GTC", transmit=False)

    target_price = round(estimated_buy_price * TAKE_PROFIT_PCT, 2)
    take_profit  = LimitOrder("SELL", qte, target_price, tif="GTC", transmit=True)

    return parent, stop_loss, take_profit


def build_buy_orders(df_signals: pd.DataFrame) -> list[dict]:
    """
    Build contract and bracket order objects for each signal row.
    Pure sync — no IB connection required.

    Returns:
        List of dicts with keys: symbol, contract, parent, stop_loss, take_profit.
    """
    orders = []
    for _, signal in df_signals.iterrows():
        contract        = Stock(signal["symbol"], "SMART", "USD")
        estimated_price = round(signal["signal_close"], 2)
        parent, stop_loss, take_profit = create_bracket_order(
            DEFAULT_QUANTITY, estimated_price
        )
        orders.append({
            "symbol":     signal["symbol"],
            "contract":   contract,
            "parent":     parent,
            "stop_loss":  stop_loss,
            "take_profit": take_profit,
        })
    return orders


def save_placed_orders(placed_orders: list[dict], filepath: Path) -> None:
    """
    Serialize placed order results to CSV.
    Captures submitted_at timestamp at save time.
    """
    submitted_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows = []
    for result in placed_orders:
        rows.append({
            "symbol":          result["symbol"],
            "submitted_at":    submitted_at,
            "parent_order_id": result["parent_trade"].order.orderId,
            "parent_status":   result["parent_trade"].orderStatus.status,
            "parent_filled_at":  None,
            "sl_order_id":     result["sl_trade"].order.orderId,
            "sl_status":       result["sl_trade"].orderStatus.status,
            "sl_filled_at":      None, 
            "tp_order_id":     result["tp_trade"].order.orderId,
            "tp_status":       result["tp_trade"].orderStatus.status,
            "tp_filled_at":      None, 
        })

    # Append if file already exists, create with header if not
    write_header = not filepath.exists()
    pd.DataFrame(rows)[PLACED_ORDERS_COLUMNS].to_csv(
        filepath, mode="a", header=write_header, index=False
    )

    print(f"💾 Saved {len(rows)} placed order(s) to {filepath}")


# ---------------------------------------------------------------------------
# Core async logic — single-unit operations
# ---------------------------------------------------------------------------

async def place_order_async(ib: IB, item: dict) -> dict:
    """
    Qualify contract and place a bracket order for a single signal.

    Yields to the event loop after placing the parent so TWS can assign
    orderId before linking children, then yields again for child acks.

    Returns:
        Dict with keys: symbol, parent_trade, sl_trade, tp_trade.
    """
    contract = item["contract"]
    parent   = item["parent"]
    sl       = item["stop_loss"]
    tp       = item["take_profit"]

    await ib.qualifyContractsAsync(contract)

    parent_trade = ib.placeOrder(contract, parent)
    await asyncio.sleep(0)          # yield → TWS assigns orderId to parent

    sl.parentId = parent.orderId
    tp.parentId = parent.orderId

    sl_trade = ib.placeOrder(contract, sl)
    tp_trade = ib.placeOrder(contract, tp)
    await asyncio.sleep(0)          # yield → TWS acks children

    print(f"✅ {item['symbol']} submitted (Parent ID: {parent.orderId})")

    return {
        "symbol":       item["symbol"],
        "parent_trade": parent_trade,
        "sl_trade":     sl_trade,
        "tp_trade":     tp_trade,
    }


# ---------------------------------------------------------------------------
# Async orchestrators
# ---------------------------------------------------------------------------

async def get_report_async(strategy: Strategy) -> pd.DataFrame | None:
    """
    Run an IBKR scanner using the provided strategy and return results.

    Returns:
        DataFrame with columns: rank, symbol, conId, localSymbol, tradingClass.
        Returns None if the scan fails.
    """
    ib  = IB()
    df  = None

    try:
        scanner = strategy.scanner()

        await ib.connectAsync(IBKR_HOST, IBKR_PORT, clientId=IBKR_CLIENT_ID)

        print("Requesting scanner data...")
        scan_data = await ib.reqScannerDataAsync(scanner)

        results = [
            {
                "rank":         d.rank,
                "symbol":       d.contractDetails.contract.symbol,
                "conId":        d.contractDetails.contract.conId,
                "localSymbol":  d.contractDetails.contract.localSymbol,
                "tradingClass": d.contractDetails.contract.tradingClass,
            }
            for d in scan_data
        ]
        df = pd.DataFrame(results)

    except Exception as e:
        print(f"❌ Error during scan: {e}")

    finally:
        ib.disconnect()

    return df


async def save_data_async(
    tickers: list,
    timeframe=None,
    back_days: int = None,
) -> None:
    """
    Fetch 1-min historical OHLCV bars for each ticker and save to CSV.

    Args:
        tickers:   List of ticker symbols (str) or conIds (int).
        timeframe: Reserved for future use.
        back_days: Reserved for future use.

    Output files: DATA/<symbol>.csv
    """
    ib = IB()

    try:
        await ib.connectAsync(IBKR_HOST, IBKR_PORT, clientId=IBKR_CLIENT_ID)
        print("Get Data Started")

        for ticker in tickers:
            # Accept either a conId (int) or a symbol string
            if isinstance(ticker, int):
                contract = Stock(conId=ticker)
            else:
                contract = Stock(ticker, "SMART", "USD")

            await ib.qualifyContractsAsync(contract)
            print(f"Fetching data for {contract.symbol}...")

            bars = await ib.reqHistoricalDataAsync(
                contract,
                endDateTime="",
                durationStr="2 D",
                barSizeSetting="1 min",
                whatToShow="TRADES",
                useRTH=False,   # include pre-market data — required for gap detection
            )

            if bars:
                df = util.df(bars)
                df["symbol"] = contract.symbol
                filepath = HISTORICAL_DATA_DIR / f"{contract.symbol}.csv"
                df.to_csv(filepath, index=False)
                print(f"💾 Saved {len(bars)} rows to {filepath}")
            else:
                print(f"⚠️  No data returned for {contract.symbol}")

            # Small sleep to avoid IBKR pacing violations
            await asyncio.sleep(0.1)

    except Exception as e:
        print(f"❌ An error occurred: {e}")

    finally:
        ib.disconnect()


async def place_orders_async() -> None:
    """
    Full order placement workflow:
      1. Load and filter buy signals (sync)
      2. Build contract + bracket order objects (sync)
      3. Connect to IB and place each bracket order (async)
      4. Wait for stable submission status on all parents
      5. Save placed orders to CSV
    """
    # --- All sync preparation before opening IB connection ---
    if not BUY_SIGNALS_FILE.exists():
        print(f"❌ {BUY_SIGNALS_FILE} not found.")
        return

    df_signals = load_buy_signals(BUY_SIGNALS_FILE)

    if df_signals.empty:
        print("⚠️  No buy signals detected. Order placement skipped.")
        return

    order_items = build_buy_orders(df_signals)
    print(f"📋 {len(order_items)} signal(s) prepared, connecting to IB...")

    # --- Open IB connection only after all data prep is validated ---
    ib = IB()
    placed_orders = []

    try:
        await ib.connectAsync(IBKR_HOST, IBKR_PORT, clientId=IBKR_CLIENT_ID)

        for item in order_items:
            try:
                result = await place_order_async(ib, item)
                placed_orders.append(result)
            except Exception as e:
                print(f"❌ {item['symbol']} failed: {e}")

        # Wait for all parents to reach a stable status before saving
        for result in placed_orders:
            trade = result["parent_trade"]
            while trade.orderStatus.status not in SUBMITTED_STATES:
                await asyncio.sleep(0.1)

    finally:
        ib.disconnect()
        if placed_orders:
            save_placed_orders(placed_orders, PLACED_ORDERS_FILE)
