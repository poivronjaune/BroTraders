import asyncio
from ib_async import IB, Stock
from brotools.config import IBKR_HOST, IBKR_PORT, IBKR_CLIENT_ID


async def get_market_price(ib: IB, contract) -> float | None:
    """
    Request a snapshot market price for a contract.
    Returns the last price, or None if unavailable.
    """
    ticker = await ib.reqMktDataAsync(contract, snapshot=True)

    # Try last price first, fall back to close price if market is closed
    price = ticker.last if ticker.last and ticker.last > 0 else ticker.close
    return price if price and price > 0 else None


async def main():
    ib = IB()
    try:
        await ib.connectAsync(IBKR_HOST, IBKR_PORT, clientId=IBKR_CLIENT_ID)

        positions = ib.positions()
        print(f"📡 Found {len(positions)} position(s).")

        for pos in positions:
            # reqMktDataAsync needs a qualified contract
            contract = Stock(pos.contract.symbol, "SMART", pos.contract.currency)
            await ib.qualifyContractsAsync(contract)

            price = await get_market_price(ib, contract)
            print(f"{pos.contract.symbol}: last={price}, avgCost={pos.avgCost}, qty={pos.position}")

    finally:
        ib.disconnect()

if __name__ == "__main__":
    asyncio.run(main())