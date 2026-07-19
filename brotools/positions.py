"""
positions.py

Connects to IBKR TWS, retrieves all current positions, fetches a
market price snapshot for each, calculates unrealized P&L, and saves
the results to DATA/5_positions.csv.

The CSV is overwritten on each run with a retrieved_at timestamp.
Run this script independently from the order-placement script.
"""

import asyncio
from datetime import datetime
from pathlib import Path

import pandas as pd
from ib_async import IB, Stock

from brotools.config import IBKR_HOST, IBKR_PORT, IBKR_CLIENT_ID

# ---------------------------------------------------------------------------
# File paths
# ---------------------------------------------------------------------------
POSITIONS_FILE = Path("DATA/5_positions.csv")

# ---------------------------------------------------------------------------
# Helpers — sync, no IB connection
# ---------------------------------------------------------------------------

def calculate_unrealized_pnl(
    avg_cost: float,
    current_price: float,
    quantity: float,
) -> float | None:
    """Calculate unrealized P&L as (current_price - avg_cost) * quantity."""
    if avg_cost is None or current_price is None or quantity is None:
        return None
    return round((current_price - avg_cost) * quantity, 4)


def build_positions_df(positions: list, prices: dict) -> pd.DataFrame:
    """
    Build a DataFrame from positions and their market prices.

    Args:
        positions: List of Position objects from ib.positions()
        prices:    Dict of symbol → current_price from market data snapshots
    """
    rows = []
    retrieved_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for pos in positions:
        symbol         = pos.contract.symbol
        avg_cost       = pos.avgCost
        quantity       = pos.position
        current_price  = prices.get(symbol)
        unrealized_pnl = calculate_unrealized_pnl(avg_cost, current_price, quantity)

        rows.append({
            "retrieved_at":   retrieved_at,
            "account":        pos.account,
            "symbol":         symbol,
            "quantity":       quantity,
            "avg_cost":       round(avg_cost, 4)       if avg_cost       is not None else None,
            "current_price":  round(current_price, 4)  if current_price  is not None else None,
            "unrealized_pnl": unrealized_pnl,
        })

    return pd.DataFrame(rows)


def save_positions(df: pd.DataFrame, filepath: Path) -> None:
    """Overwrite positions CSV on each run."""
    df.to_csv(filepath, index=False)
    print(f"💾 Saved {len(df)} position(s) to {filepath}")


# ---------------------------------------------------------------------------
# Core async logic
# ---------------------------------------------------------------------------

async def get_market_price(ib: IB, contract) -> float | None:
    """
    Request a snapshot market price for a contract.
    Tries last price first, falls back to close price if market is closed.
    Returns None if no price is available.
    """
    ticker = await ib.reqMktDataAsync(contract, snapshot=True)

    # last → live market price; close → most recent closing price
    price = ticker.last if ticker.last and ticker.last > 0 else ticker.close
    return price if price and price > 0 else None


async def fetch_prices(ib: IB, positions: list) -> dict:
    """
    Qualify contracts and fetch market price snapshots for all positions.

    Returns:
        Dict of symbol → current_price (None if unavailable)
    """
    prices = {}
    for pos in positions:
        contract = Stock(pos.contract.symbol, "SMART", pos.contract.currency)
        await ib.qualifyContractsAsync(contract)

        price = await get_market_price(ib, contract)

        if price is None:
            print(f"⚠️  No market price available for {pos.contract.symbol}")
        else:
            print(f"📈 {pos.contract.symbol}: price={price}, avgCost={pos.avgCost}, qty={pos.position}")

        prices[pos.contract.symbol] = price

    return prices


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

async def track_positions_async() -> None:
    """
    Main async entry point.

    1. Connect to IBKR and fetch positions
    2. Fetch market price snapshot for each position
    3. Calculate unrealized P&L
    4. Save to CSV
    """
    ib = IB()
    try:
        await ib.connectAsync(IBKR_HOST, IBKR_PORT, clientId=IBKR_CLIENT_ID)

        positions = ib.positions()

        if not positions:
            print("⚠️  No open positions found.")
            return

        print(f"📡 Found {len(positions)} position(s).")

        prices = await fetch_prices(ib, positions)

    finally:
        ib.disconnect()

    # Build and save — done outside the IB connection
    df = build_positions_df(positions, prices)
    save_positions(df, POSITIONS_FILE)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    asyncio.run(track_positions_async())