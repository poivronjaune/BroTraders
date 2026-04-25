import sys
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

from brotools import get_strategy_list, to_pascal_case, load_tickers_list
from brotools.config import IBKR_HOST, IBKR_PORT, IBKR_CLIENT_ID
from brotools.services import ibkr_subscription_async, ibkr_get_price_data
from brotools.strat_gap_rise import strategy


async def automated_bot(strategy_instance):
    ib = IB()
    try:
        # 1. Connect once, this will start the asynchronous loop
        await ib.connectAsync(IBKR_HOST, IBKR_PORT, clientId=IBKR_CLIENT_ID)
        
        # 2. Run the IBKR Market Scan and store in the prospects.json file under /DATA
        match strategy_instance.ticker_source:
            case 'IBKR_Subscription':
                prospects = await ibkr_subscription_async(ib, strategy_instance)
            case 'Symbols_List':
                pass

        # 3. Get Price Data From IBKR, add indicators and buy_signals
        # df_prospects = load_tickers_list()
        df_prospects = pd.DataFrame(prospects).set_index('symbol')
        buy_signals = []
        for ticker in df_prospects.index.to_list():
            filename = await ibkr_get_price_data(ib, ticker) # Data stored on disk
            if filename:
                df_prospects.at[ticker, 'data_file'] = filename
            
                # 4. Calculate indicators from strategy definition

                # 5. Generate signals from strategy conditions
                buy_signal = strategy_instance.signals(ticker, df_prospects, gap_threshold=10.0)
                if buy_signal is None:
                    continue
                buy_signals.append(buy_signal)
                
        df_prospects.reset_index().to_json('DATA/prospects.json', orient='records', indent=4, force_ascii=False)            
        with open('DATA/buy_signals.json', 'w') as f:
            json.dump(buy_signals, f, indent=4)
        
        # 6. Calulate orders from generated signals
        
        # 7. Place Orders
    except Exception as e:
        print(f"Application Error: {e}")
    finally:
        # 3. Disconnect gracefully within the async loop
        if ib.isConnected():
            ib.disconnect()    
    

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
        module = importlib.import_module(module_path)
        class_name = to_pascal_case(strategy_name)
        strategy_class = getattr(module, class_name)
        strategy_instance = strategy_class()
        print(strategy_instance.name)
        asyncio.run(automated_bot(strategy_instance))
        #asyncio.run(get_report_async())        
    except ImportError as e:
        print(f"[!] Error: Could not find module at {module_path} \n{e}")
    except AttributeError as e:
        print(f"[!] Error: Module '{strategy_name}' does not contain class '{class_name}'\n{e}")        
        
    return

if __name__ == "__main__":
    df_prospects = load_tickers_list()
    symbols = df_prospects.index.to_list()
    print(df_prospects)
    print(symbols)