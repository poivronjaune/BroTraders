import asyncio
import pandas as pd
from ib_async import *

from brotools.config import IBKR_HOST, IBKR_PORT, IBKR_CLIENT_ID
from brotools.async_services import get_report_async, save_data_async
from brotools.strategies.gap_rise import Strategy


def get_data(tickers: list[str]):
    tickers = pd.read_csv("DATA/1_scan_results.csv")["symbol"].tolist()
    asyncio.run(save_data_async(tickers)) # Save csv files to disk

if __name__ == "__main__":
    tickers = pd.read_csv("DATA/1_scan_results.csv")["symbol"].tolist()
    get_data(tickers)
