import sys
import time
import glob
import asyncio
import json
import pandas as pd
import importlib

from datetime import datetime
from ib_async import *
from pprint import pprint
from dataclasses import asdict # ib_async objects are often dataclasses so they can be easily converted to dicts for JSON serialization
from decimal import Decimal
from pathlib import Path

from brotools import get_strategy_list, to_pascal_case
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
        sub.locationCode = 'STK.US.MAJOR'
        #sub.scanCode    = 'TOP_PERC_GAIN'        
        sub.scanCode     = 'HIGH_OPEN_GAP'
        sub.abovePrice   = 2
        sub.belowPrice   = 500
        sub.aboveVolume  = 100000        # 1 Millions transactions, 100 000 is 100k, 10 000 is 10k
        sub.marketCapAbove = 300         # Small Market Capitalisation and above
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


def save_orders_to_json(orders_list, filename='DATA/submitted_orders.json'):
    """Converts ib_async Order objects to dictionaries and saves to JSON."""
    
    def decimal_default(obj):
        if isinstance(obj, Decimal):
            return float(obj) # Convert Decimals to floats for JSON compatibility
        raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")

    serializable_orders = []
    for order_group in orders_list:
        p = asdict(order_group["parent"])
        s = asdict(order_group["stop_loss"])
        t = asdict(order_group["take_profit"])

        entry = {
            # parent
            "p_orderId": p["orderId"],
            "p_action": p["action"],
            "p_totalQuantity": p["totalQuantity"],
            "p_orderType": p["orderType"],
            "p_lmtPrice": p["lmtPrice"],
            "p_auxPrice": p["auxPrice"],
            "p_tif": p["tif"],
            "p_outsideRth": p["outsideRth"],

            # stop loss
            "s_orderId": s["orderId"],
            "s_action": s["action"],
            "s_totalQuantity": s["totalQuantity"],
            "s_orderType": s["orderType"],
            "s_lmtPrice": s["lmtPrice"],
            "s_auxPrice": s["auxPrice"],
            "s_tif": s["tif"],
            "s_parentId": s["parentId"],
            "s_outsideRth": s["outsideRth"],

            # take profit
            "t_orderId": t["orderId"],
            "t_action": t["action"],
            "t_totalQuantity": t["totalQuantity"],
            "t_orderType": t["orderType"],
            "t_lmtPrice": t["lmtPrice"],
            "t_auxPrice": t["auxPrice"],
            "t_tif": t["tif"],
            "t_parentId": t["parentId"],
            "t_outsideRth": t["outsideRth"],
        }

        serializable_orders.append(entry)
    
    with open(filename, 'w') as f:
        json.dump(serializable_orders, f, indent=4, default=decimal_default)
    print(f"📂 Saved {len(orders_list)} order brackets to {filename}")
    
   
async def place_orders_async():
    ib = IB()
    orders = []
    try:
        # 1. Connect ONCE outside the loop and load buy signals
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
            
            order = {"parent": parent, "stop_loss": stop_loss, "take_profit": take_profit}
            orders.append(order)
                    
            # Small async sleep to let the event loop process network traffic
            await asyncio.sleep(0.5)
            
            print(f"✅ Bracket submitted for {signal['symbol']} (Parent ID: {parent.orderId})")

    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        # 5. Disconnect AFTER all loop iterations are done
        ib.disconnect()
        if len(orders) > 0:
            save_orders_to_json(orders)
    
    
def place_orders():
    asyncio.run(place_orders_async())

async def monitor_trades_async():
    ib = IB()   
    try:
        # 1. Connect ONCE outside the loop and load buy signals
        await ib.connectAsync(IBKR_HOST, IBKR_PORT, clientId=IBKR_CLIENT_ID)
        
        #await ib.reqAllOpenOrders()  # Only call this if there is probability of IB() not obtaining orders on connect.

        print("--- Active Orders ---")
        idx = 1
        for trade in ib.trades():
            print("========================================================================================")
            print(f"Trade #:{idx}")
            print(trade) 
            idx += 1
             
    except Exception as e:
        print(f"❌ Error: {e}")              
    finally:    
        ib.disconnect()
    

def track_orders_and_positions():
    # get IBKR Open Positions
    # get IBKR trades for the day ?
    # Log trades with P&L in a csv file
    asyncio.run(monitor_trades_async())
    

def close_positions():
    ib = IB()
    ib.connect(IBKR_HOST, IBKR_PORT, clientId=IBKR_CLIENT_ID)
    
    # --- Cancel all open orders ---
    open_orders = ib.openOrders()
    for o in open_orders:
        ib.cancelOrder(o)
        print(f"Cancelled order: {o.action} {o.totalQuantity} {o.orderType}")    
    
    ib.disconnect()

##########################################################################################
#
# NEW Refactored strategy run architecture
#
##########################################################################################

async def scan_report_async(ib, strategy_instance):
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
        sub.locationCode = 'STK.US.MAJOR'
        #sub.scanCode    = 'TOP_PERC_GAIN'        
        sub.scanCode     = 'HIGH_OPEN_GAP'
        sub.abovePrice   = 10
        sub.belowPrice   = 200
        sub.aboveVolume  = 100000        # 1 Millions transactions, 100 000 is 100k, 10 000 is 10k
        sub.marketCapAbove = 300         # Small Market Capitalisation and above
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


def print_app_name():
    print("┌───────────────────────────────────────────────────────┐")
    print("│    BROTOOLS: AUTOMATED TRADING                        │")
    print("└───────────────────────────────────────────────────────┘") 
       
def error_msg(err_msg, extra:list=[]):
    print_app_name()
    print(f"\n[!] Error: {err_msg}")
    print("Usage: run <strategy_name>")
    print(f"\nAvailable strategies:")
    print(*extra, sep='\n') # Print a list of items one per row
    print(" ")
          
def main():
    # Setup, load strategy and run the trading bot
    strategy_list = get_strategy_list()
        
    if len(sys.argv) < 2:
        error_msg('No strategy selected.', extra=strategy_list)
        return

    strategy_name = sys.argv[1]
    if strategy_name not in strategy_list:
        error_msg('Bad strategy name', extra=strategy_list)
        return  
    
    print_app_name()
    print(f"Selected Strategy: {strategy_name}\n")
    
    module_path = f"brotools.strategies.{strategy_name}"
    
    try:
        ib = IB()
        module = importlib.import_module(module_path)
        class_name = to_pascal_case(strategy_name)
        strategy_class = getattr(module, class_name)
        strategy_instance = strategy_class()
        print(strategy_instance.name)
        asyncio.run(scan_report_async(ib, strategy_instance))
        #asyncio.run(get_report_async())        
    except ImportError as e:
        print(f"[!] Error: Could not find module at {module_path} \n{e}")
    except AttributeError as e:
        print(f"[!] Error: Module '{strategy_name}' does not contain class '{class_name}'\n{e}")        
    finally:
        ib.disconnect()
        
    return

if __name__ == "__main__":
    main()
    