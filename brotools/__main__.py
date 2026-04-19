import sys
import time
import glob
import asyncio
import json
import pandas as pd

from datetime import datetime
from ib_async import *
from pprint import pprint

from brotools.config import IBKR_HOST, IBKR_PORT, IBKR_CLIENT_ID
from brotools.strat_gap_rise import strategy


def load_tickers():
    with open('DATA/results.json', 'r') as f:
        symbols = json.load(f)
        
    tickers = [t['symbol'] for t in symbols]
    
    return tickers

async def get_data_async():
    ib = IB()
    try:
        # 1. Connect ONCE using the async method
        await ib.connectAsync(IBKR_HOST, IBKR_PORT, clientId=IBKR_CLIENT_ID)

        tickers = load_tickers()
        
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

def getdata():
    asyncio.run(get_data_async())


async def get_report_async():
    ib = IB()
    try:
        # 1. Use connectAsync
        await ib.connectAsync(IBKR_HOST, IBKR_PORT, clientId=IBKR_CLIENT_ID)

        #sub = ScannerSubscription(
        #    numberOfRows=30,
        #    instrument='STK',
        #    locationCode='STK.NASDAQ',
        #    #scanCode='TOP_PERC_GAIN',
        #    scanCode='HIGH_OPEN_GAP',
        #    abovePrice=2,
        #    belowPrice=20,
        #    aboveVolume=10000000)
        sub = ScannerSubscription()
        sub.numberOfRows = 50
        sub.instrument   = 'STK'
        sub.locationCode = 'STK.NASDAQ'
        #sub.scanCode    = 'TOP_PERC_GAIN'        
        sub.scanCode     = 'HIGH_OPEN_GAP'
        sub.abovePrice   = 20
        sub.belowPrice   = 1000
        #sub.aboveVolume    = 1000000    # 1 Millions transactions
        #sub.marketCapAbove = 300        # Small Market Capitalisation and above
        #sub.marketCapBelow = 10000      # Medium Market Capitalisation and below (Excludes large cap that start at 10 000)        

        # 2. Use reqScannerDataAsync to wait for the results
        print("Requesting scanner data...")
        scanData = await ib.reqScannerDataAsync(sub)    

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
        with open('DATA/results.json', 'w') as f:
            json.dump(results, f, indent=4)
            
        print(f"Success: {len(results)} items saved to DATA/results.json")
    except Exception as e:
        print(f"Error during scan: {e}")
    finally:
        # 4. Always disconnect
        ib.disconnect()    

def getreport():
    asyncio.run(get_report_async())


def signals():
    # Loop through json in rank order 
    # Open minute data csv file in pandas
    # Calculate gap and percentage
    # Look at 3 candles
    # if all positive add to buy list
    
    # Load resulst.json
    prospects = load_tickers()
    buy_signals = []
    for prospect in prospects:
        csv_files = glob.glob(f"DATA/{prospect}_1min_*.csv")
        if len(csv_files) > 0:
            df = pd.read_csv(csv_files[0])
        else:
            continue
        # TODO: Add error handling
        buy_signal = strategy(prospect, df, gap_threshold=10.0)
        
        if buy_signal is None:
            continue
        
        buy_signals.append(buy_signal)

    with open('DATA/buy_signals.json', 'w') as f:
        json.dump(buy_signals, f, indent=4)


def create_bracket_order(qte, estimated_buy_price):
    # Build a bracket order to be called with a contract later in the code
    # use a small sleep() delay since we are in synchronous mode
    #parent = LimitOrder('BUY', qte, limit_price)
    parent = MarketOrder('BUY', 1, tif='GTC', transmit=False)
    # parent.orderId = ib.client.getReqId()
    
    # Stop loss
    stop_price = round(estimated_buy_price * 0.98, 2)
    stopLoss = StopOrder('SELL', qte, stop_price, tif='GTC', transmit = False)

    # Take profit
    target_price = round(estimated_buy_price * 1.05, 2)
    takeProfit = LimitOrder('SELL', qte, target_price, tif='GTC', transmit = True)

    return parent, stopLoss, takeProfit

   
async def place_trades_async():
    ib = IB()
    try:
        # 1. Connect ONCE outside the loop
        await ib.connectAsync(IBKR_HOST, IBKR_PORT, clientId=IBKR_CLIENT_ID)

        df_signals = pd.read_json('DATA/buy_signals.json')
        df_signals = df_signals[df_signals['threshold_reached'] == True]
        
        for index, signal in df_signals.iterrows():
            contract = Stock(signal['symbol'], 'SMART', 'USD')
            
            # 2. Qualify the contract (Crucial for ib_async)
            await ib.qualifyContractsAsync(contract)
            
            qte = 1
            estimated_buy_price = round(signal['open_curr'], 2)
            
            # 3. Build orders
            parent, stop_loss, take_profit = create_bracket_order(qte, estimated_buy_price)
            
            # 4. Place parent first to generate its orderId
            ib.placeOrder(contract, parent)
            
            # Link children to parentId
            stop_loss.parentId = parent.orderId
            take_profit.parentId = parent.orderId
            
            # Place children
            ib.placeOrder(contract, stop_loss)
            ib.placeOrder(contract, take_profit)
            
            # Small async sleep to let the event loop process network traffic
            await asyncio.sleep(0.5)
            
            print(f"✅ Bracket submitted for {signal['symbol']} (Parent ID: {parent.orderId})")

    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        # 5. Disconnect AFTER all loop iterations are done
        ib.disconnect()
    
def place_trades():
    asyncio.run(place_trades_async())

   

def track_portfolio():
    # get IBKR Open Positions
    # get IBKR trades for the day ?
    # Log trades with P&L in a csv file
    pass

def close_positions():
    ib = IB()
    ib.connect(IBKR_HOST, IBKR_PORT, clientId=IBKR_CLIENT_ID)
    
    # --- Cancel all open orders ---
    open_orders = ib.openOrders()
    for o in open_orders:
        ib.cancelOrder(o)
        print(f"Cancelled order: {o.action} {o.totalQuantity} {o.orderType}")    
    
    ib.disconnect()
    
def main():
    print("Hello, BroTools!")
    print("This is the main entry point of the application.")
    # You can add more functionality here as needed.
    
if __name__ == "__main__":
    main()
    