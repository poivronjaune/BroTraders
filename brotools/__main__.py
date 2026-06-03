import sys
import time
import glob
import asyncio
import json
import importlib
import pandas as pd

from datetime import datetime
from ib_async import *
from pprint import pprint

from brotools.config import IBKR_HOST, IBKR_PORT, IBKR_CLIENT_ID, STRATEGY_FILE
from brotools.services import get_report_async, save_data_async, place_orders_async

# Make sure strategy file exists before running
module_name = STRATEGY_FILE.replace('.py', '')
try:
    strategy_module = importlib.import_module(f"brotools.strategies.{module_name}")
    Strategy = strategy_module.Strategy
except (ModuleNotFoundError, AttributeError) as e:
    raise RuntimeError(f"Could not load strategy '{module_name}': {e}")


def get_scan():
    with Strategy() as strategy:
        scan_result = asyncio.run(get_report_async(strategy))
        if scan_result is not None:
            scan_result["strategy"] = strategy.name
            scan_result.to_csv("DATA/1_scan_results.csv", index=False)
            print(f"Scan report saved {len(scan_result)} prospects to DATA/1_scan_results.csv")

def get_data() -> None:
    # Retreive price data for a list of tickers
    #TODO Add timeframe and back_days as parameters from Strategy class
    #tickers = load_tickers_from_results()
    tickers = pd.read_csv("DATA/1_scan_results.csv")["symbol"].tolist()
    asyncio.run(save_data_async(tickers))

def add_indicators() -> None:
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
   
def get_signals():
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
  
def place_orders():
    asyncio.run(place_orders_async())

def main():
    print("Hello, BroTools!")
    print("This is the main entry point of the application.")
    print("Live trading not implemented, use commands:")
    print("  scan: get market scanner and save results")
    print("  data: get historical price data for tickers in scan results")
    print("  indicators: add technical indicators to price data")
    print("  signals: generate buy signals based on indicators and save to file")
    print("  orders: place orders for buy signals")
    
if __name__ == "__main__":
    main()
    