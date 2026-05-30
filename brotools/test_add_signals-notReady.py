import asyncio
import pandas as pd
from ib_async import *

from brotools.config import IBKR_HOST, IBKR_PORT, IBKR_CLIENT_ID
from brotools.async_services import get_report_async, save_data_async
from brotools.strategies.gap_rise import Strategy


if __name__ == "__main__":
    tickers = pd.read_csv("DATA/1_scan_results.csv")["symbol"].tolist()
    buy_signals = []
    with Strategy() as strategy:
        for ticker in tickers:
            df_data = pd.read_csv(
                f"DATA/{ticker}.csv", 
                index_col="date",  # Sets this column as the row labels (index)
                parse_dates=["date"]  # Forces pandas to convert strings to true Timestamp objects
            )        
            print(df_data.tail())
            df_data = strategy.add_signal(df_data)
            print(df_data.tail())
            break
