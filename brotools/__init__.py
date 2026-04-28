import json
import csv
import pandas as pd
import numpy as np
import xml.etree.ElementTree as ET

from pathlib import Path
from ib_async import *

from brotools.config import IBKR_HOST, IBKR_PORT, IBKR_CLIENT_ID


def to_pascal_case(snake_str):
    """Converts strategy_open_gap_up to StrategyOpenGapUp"""
    return "".join(word.capitalize() for word in snake_str.split("_")) 

def to_serializable(obj):
    if isinstance(obj, (float, np.float64)):
        return round(float(obj), 2)
    if isinstance(obj, (bool, np.bool_)):
        return bool(obj)
    if isinstance(obj, list):
        return [to_serializable(i) for i in obj]
    if isinstance(obj, dict):
        return {k: to_serializable(v) for k, v in obj.items()}
    
    return obj



def get_strategy_list():
    # Define the directory
    strat_dir = Path("brotools/strategies")
    
    # 1. glob("s_*") finds everything starting with s_
    # 2. .stem gets the filename without the extension (e.g., .py)
    # 3. is_file() ensures we don't accidentally pick up folders
    strategies = [f.stem for f in strat_dir.glob("strategy_*") if f.is_file()]

    return strategies


def load_tickers_list(filename='DATA/prospects.json') -> pd.DataFrame:
    #with open(filename, 'r') as f:
    #    symbols = json.load(f)
    #    
    #tickers = [t['symbol'] for t in symbols]
    df_tickers = pd.read_json(filename).set_index('symbol')
    
    return df_tickers



def print_tree(element, level=0):
    indent = "  " * level
    content = element.text.strip() if element.text else ""
    
    # Print the tag and content if it exists
    if content:
        print(f"{indent}{element.tag}: {content}")
    else:
        print(f"{indent}{element.tag}")
        
    # Recurse through children
    for child in element:
        print_tree(child, level + 1)
        
def list_available_subscriptions():
    '''List all ScannerSubscriptions that can be used on Stocks (instruments contains STK)'''
    ib = IB()
    ib.connect(IBKR_HOST, IBKR_PORT, clientId=IBKR_CLIENT_ID)

    # This returns a massive XML string of all parameters
    xml_params = ib.reqScannerParameters()
    ib.sleep(0.2)
    ib.disconnect()
    
    # Quick way to see all scanCodes
    tree = ET.fromstring(xml_params)
    #print_tree(tree)

    
    scanner_data = []
    for config in tree.findall('.//ScanType'):
        scan_code = config.findtext('scanCode')
        desc = config.findtext('displayName', "n.a.")
        access = config.findtext('access', "n.a.")
        instruments = config.findtext('instruments', 'n.a.')
        
        if scan_code:
            # Create a dictionary for this row
            row = {
                "ScanCode": scan_code,
                "Access": access,
                "Description": desc,
                "Instruments": instruments
            }
            if 'STK' in instruments:
               scanner_data.append(row)
    
    csv_file = "ibkr_scanners.csv"
    
    if scanner_data:
        # Extract keys from the first dict to use as headers
        keys = scanner_data[0].keys()
        
        with open(csv_file, 'w', newline='', encoding='utf-8') as output_file:
            dict_writer = csv.DictWriter(output_file, fieldnames=keys)
            dict_writer.writeheader()
            dict_writer.writerows(scanner_data)
        
        print(f"Successfully saved {len(scanner_data)} scanners to {csv_file}")
    else:
        print("No data found to save.")    
    
    #codes = [c.text for c in tree.findall('.//scanCode')]
    #print(*codes, sep="\n")
    