import sys
import time
import glob
import asyncio
import json
import pandas as pd

from datetime import datetime
from ib_async import IB, Stock, util


from brotools.config import IBKR_HOST, IBKR_PORT, IBKR_CLIENT_ID
from brotools.strategies.gap_rise import Strategy

########################################
# Utility functions 
########################################
def save_report_to_json(results):
        with open('DATA/results.json', 'w') as f:
            json.dump(results, f, indent=4)
            
        print(f"Success: {len(results)} items saved to DATA/results.json")

def load_tickers_from_results():
    with open('DATA/results.json', 'r') as f:
        symbols = json.load(f)
        
    tickers = [t['symbol'] for t in symbols]
    
    return tickers


#########################################
# IBKR Async functions
#########################################

async def get_report_async(strategy) -> list:
    ib = IB()
    try:
        # Get a scanner object from the stratgey passed in parameter
        scanner = strategy.scanner()

        # 0. Use connectAsync
        await ib.connectAsync(IBKR_HOST, IBKR_PORT, clientId=IBKR_CLIENT_ID)

        # 2. Use reqScannerDataAsync to wait for the results
        print("Requesting scanner data...")
        scanData = await ib.reqScannerDataAsync(scanner)    

        results = [
            {
                "rank": d.rank,
                "conId": d.contractDetails.contract.conId,
                "symbol": d.contractDetails.contract.symbol,
                "localSymbol": d.contractDetails.contract.localSymbol,
                "tradingClass": d.contractDetails.contract.tradingClass
            }
            for d in scanData
        ]

    except Exception as e:
        print(f"Error during scan: {e}")
        return None
    finally:
        # 4. Always disconnect
        ib.disconnect()  
        return results


async def get_data_async(tickers, timeframe= None, back_days=None):
    ib = IB()
    try:
        # 1. Connect ONCE using the async method
        await ib.connectAsync(IBKR_HOST, IBKR_PORT, clientId=IBKR_CLIENT_ID)
        
        for ticker in tickers:
            # Check if ticker is a conId (int) or symbol (str) based on our previous talk
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
                filename = f"DATA/{contract.symbol}_1min_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
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