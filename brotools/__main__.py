import sys
import time
import glob
import asyncio
import json
import pandas as pd

from datetime import datetime
from ib_async import *
from pprint import pprint
from dataclasses import asdict # ib_async objects are often dataclasses so they can be easily converted to dicts for JSON serialization
from decimal import Decimal

from brotools.services import load_tickers_from_results, get_data_async
from brotools.async_services import get_report_async, save_data_async, place_orders_async

from brotools.config import IBKR_HOST, IBKR_PORT, IBKR_CLIENT_ID
from brotools.strat_gap_rise import strategy
from brotools.strategies.gap_rise import Strategy

def get_scan_report():
    with Strategy() as strategy:
        scan_result = asyncio.run(get_report_async(strategy))
        if scan_result is not None:
            #save_report_to_json(result)
            scan_result.to_csv("DATA/1_scan_results.csv", index=False)

def get_data() -> None:
    # Retreive price data for a list of tickers
    #TODO Add timeframe and back_days as parameters from Strategy class
    #tickers = load_tickers_from_results()
    tickers = pd.read_csv("DATA/1_scan_results.csv")["symbol"].tolist()
    asyncio.run(save_data_async(tickers))

def add_indicators() -> None:
    strategy = Strategy()
    tickers = pd.read_csv("DATA/1_scan_results.csv")["symbol"].tolist()
    with Strategy() as strategy:
        for ticker in tickers:
            df_data = pd.read_csv(
                f"DATA/{ticker}.csv", 
                index_col="date",  # Sets this column as the row labels (index)
                parse_dates=["date"]  # Forces pandas to convert strings to true Timestamp objects
            )     
            
            df_data = strategy.add_indicators(df_data)
            df_data.to_csv(f'DATA/{ticker}.csv')
            print(df_data.head())     
   
def signals():
    csv_path = "DATA/1_scan_results.csv"
    df_scan_results = pd.read_csv(csv_path)
    tickers = df_scan_results["symbol"].tolist()
    
    trace_data_list = []
    with Strategy() as strategy:
        for ticker in tickers:
            df_data = pd.read_csv(f"DATA/{ticker}.csv", index_col="date", parse_dates=["date"]) 
            conditions_trace = strategy.is_buy_signal(df_data)
            trace_data_list.append(conditions_trace)
    
    # House keeping to save data columns in specific order
    df_traces = pd.DataFrame(trace_data_list)
    df_scan_results = df_scan_results.set_index("symbol")
    df_traces = df_traces.set_index("symbol")
    df_scan_results = df_traces.combine_first(df_scan_results)
    
    df_scan_results = df_scan_results.reset_index()
    front_cols = ["rank", "symbol", "conId", "localSymbol", "tradingClass"]
    original_cols = [col for col in front_cols if col in df_scan_results.columns]
    other_cols = [col for col in df_scan_results.columns if col not in original_cols]
    df_scan_results = df_scan_results[original_cols + other_cols]
    df_scan_results.to_csv("DATA/2_buy_signals.csv", index=False)
     
    buy_signals = df_scan_results[df_scan_results["buy_signal"] == True]["symbol"].tolist()
    print(buy_signals)    

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
            "symbol": order_group["symbol"],
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

def place_orders():
    df_signals = pd.read_csv('DATA/2_buy_signals.csv')
    df_signals = df_signals[df_signals['buy_signal'] == True]

    # TODO Implement loop to place orders for each signal in the dataframe       



#async def place_orders_async():
#    ib = IB()
#    orders = []
#    try:
#        # 1. Connect ONCE outside the loop and load buy signals
#        await ib.connectAsync(IBKR_HOST, IBKR_PORT, clientId=IBKR_CLIENT_ID)
#
#        df_signals = pd.read_json('DATA/buy_signals.json')
#        df_signals = df_signals[df_signals['threshold_reached'] == True]
#        
#        for index, signal in df_signals.iterrows():
#            contract = Stock(signal['symbol'], 'SMART', 'USD')
#            
#            # 2. Qualify the contract (Crucial for ib_async)
#            await ib.qualifyContractsAsync(contract)
#            
#            qte = 1
#            estimated_buy_price = round(signal['open_curr'], 2)
#            
#            # 3. Build orders
#            parent, stop_loss, take_profit = create_bracket_order(qte, estimated_buy_price)
#            
#            # 4. Place parent first to generate its orderId
#            ib.placeOrder(contract, parent)
#            
#            # Link children to parentId
#            stop_loss.parentId = parent.orderId
#            take_profit.parentId = parent.orderId
#            
#            # Place children
#            ib.placeOrder(contract, stop_loss)
#            ib.placeOrder(contract, take_profit)
#            
#            order = {"symbol":signal['symbol'], "parent": parent, "stop_loss": stop_loss, "take_profit": take_profit}
#            orders.append(order)
#                    
#            # Small async sleep to let the event loop process network traffic
#            await asyncio.sleep(0.5)
#            
#            print(f"✅ Bracket submitted for {signal['symbol']} (Parent ID: {parent.orderId})")
#
#    except Exception as e:
#        #TODO: Do we want to track ordaers that failed in our file?
#        print(f"❌ Error: {e}")
#    finally:
#        # 5. Disconnect AFTER all loop iterations are done
#        ib.disconnect()
#        if len(orders) > 0:
#            save_orders_to_json(orders)
    
#def place_orders():
#    asyncio.run(place_orders_async())

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
    
def main():
    print("Hello, BroTools!")
    print("This is the main entry point of the application.")
    # You can add more functionality here as needed.
    
if __name__ == "__main__":
    main()
    