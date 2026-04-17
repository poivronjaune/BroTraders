import asyncio
from ib_async import IB, Stock
from brotools.config import IBKR_HOST, IBKR_PORT, IBKR_CLIENT_ID

# 1. Define the callback function
def on_ticker_update(ticker):
    # This fires every time a new 'tick' (price change) is received
    if ticker.last:  # Simple check to ensure we have a price
        print(f"Update: {ticker.contract.symbol} | Last: {ticker.last} | Bid: {ticker.bid} | Ask: {ticker.ask}")

async def main():
    ib = IB()
    
    # 2. Connect (using async connect)
    # 7497 is usually the default for Paper Trading
    await ib.connectAsync(IBKR_HOST, IBKR_PORT, clientId=IBKR_CLIENT_ID)

    # 3. Setup and Qualify Contract
    contract = Stock('AAPL', 'SMART', 'USD')
    await ib.qualifyContractsAsync(contract)

    # 4. Request the market data stream
    ticker = ib.reqMktData(contract)

    # 5. Attach the event listener
    ticker.updateEvent += on_ticker_update

    print("Streaming live data... Press Ctrl+C to stop.")

    # 6. Keep the script running forever (or until interrupted)
    while True:
        await asyncio.sleep(1)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nDisconnected.")