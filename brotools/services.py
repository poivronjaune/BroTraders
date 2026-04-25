import json
import asyncio
import pandas as pd
from datetime import datetime

from ib_async import Stock, util

# TODO: Remove HARD CODED DATA folder and names

async def ibkr_subscription_async(ib, strategy_instance):
    try:
        print(f"Requesting scanner data for: {strategy_instance.name}")
        scanData = await ib.reqScannerDataAsync(strategy_instance.subscription)

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
        
        # 3. Save to file
        with open('DATA/prospects.json', 'w') as f:
            json.dump(results, f, indent=4)
        
        print(f"Success: {len(results)} items saved to DATA/prospects.json")
        return results
    except Exception as e:
        print(f"Error during scan execution: {e}")
        return []
        
        
async def ibkr_get_price_data(ib, ticker, bar_size='1 min', back_days='2 D'):
    try:
        contract = Stock(ticker, "SMART", "USD")
        await ib.qualifyContractsAsync(contract)
        print(f"Fetching data for {contract.symbol}...")
        bars = await ib.reqHistoricalDataAsync(
            contract,
            endDateTime="",
            durationStr=back_days,
            barSizeSetting=bar_size,
            whatToShow="TRADES",
            useRTH=False    # Crucial for Gaps: gets Pre-Market data
        )    
        if bars:
            df = util.df(bars)
            folder = "DATA/"
            fname = f"{contract.symbol}_1min_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
            filename = folder + fname
            df.to_csv(filename, index=False)
            print(f"Saved {len(bars)} rows to {filename}")
            return fname
        else:
            print(f"No data returned for {contract.symbol}")        
            return None
        await asyncio.sleep(0.1)
    except Exception as e:
        print(f"ERROR Laoding Price Data from IBKR")
        return None
        