import pandas as pd
import asyncio
from datetime import datetime

from ib_async import IB, Stock, util

from brotools.config import IBKR_HOST, IBKR_PORT, IBKR_CLIENT_ID
from brotools.strategies.gap_rise import Strategy

async def get_report_async(strategy: Strategy) -> pd.DataFrame | None:
    ib = IB()
    df = None

    try:
        # Get the strategy class and obtain a scanner object
        #strategy = Strategy()
        scanner = strategy.scanner()

        # 0. Use connectAsync
        await ib.connectAsync(IBKR_HOST, IBKR_PORT, clientId=IBKR_CLIENT_ID)
        
        # 1. Use reqScannerDataAsync to wait for the results
        print("Requesting scanner data...")
        scan_data = await ib.reqScannerDataAsync(scanner)  

        #2. Extract relevant info into a list of dicts, then create a DataFrame
        results = [
            {
                "rank": d.rank,
                "symbol": d.contractDetails.contract.symbol,
                "conId": d.contractDetails.contract.conId,
                "localSymbol": d.contractDetails.contract.localSymbol,
                "tradingClass": d.contractDetails.contract.tradingClass,
            }
            for d in scan_data
        ]
        df = pd.DataFrame(results)
    except Exception as e:
        print(f"Error during scan: {e}")
    finally:
        # 4. Always disconnect
        ib.disconnect() 

    return df

async def save_data_async(tickers, timeframe= None, back_days=None):
    ib = IB()
    try:
        # 1. Connect ONCE using the async method
        await ib.connectAsync(IBKR_HOST, IBKR_PORT, clientId=IBKR_CLIENT_ID)
        print(f"Get Data Started")
        
        for ticker in tickers:
            # Check if ticker is a conId (int) or symbol (str)
            if isinstance(ticker, int):
                contract = Stock(conId=ticker)
            else:
                contract = Stock(ticker, "SMART", "USD")

            # 2. Qualify the contract to ensure we have the right details
            await ib.qualifyContractsAsync(contract)
            print(f"Fetching data for {contract.symbol}...")

            # 3. Use the Async version of historical data request
            bars = await ib.reqHistoricalDataAsync(
                contract,
                endDateTime="",
                durationStr="2 D",
                barSizeSetting="1 min",
                whatToShow="TRADES",
                useRTH=False  # Crucial for Gaps: gets Pre-Market data
            )

            if bars:
                df = util.df(bars)
                df['symbol'] = contract.symbol
                #filename = f"DATA/{contract.symbol}_1min_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
                filename = f"DATA/{contract.symbol}.csv"
                df.to_csv(filename, index=False)
                print(f"Saved {len(bars)} rows to {filename}")
            else:
                print(f"No data returned for {contract.symbol}")

            # 4. Small sleep to avoid hitting IBKR pacing violations
            await asyncio.sleep(0.1)            
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        # 5. Always disconnect in the finally block
        ib.disconnect()             