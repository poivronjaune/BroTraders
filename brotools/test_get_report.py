import asyncio
import pandas as pd
from ib_async import *

from brotools.config import IBKR_HOST, IBKR_PORT, IBKR_CLIENT_ID
from brotools.async_services import get_report_async
from brotools.strategies.gap_rise import Strategy

# async def get_report_async():
#     ib = IB()
#     try:
#         # Get the strategy class and obtain a scanner object
#         strategy = Strategy()
#         scanner = strategy.scanner()

#         # 0. Use connectAsync
#         await ib.connectAsync(IBKR_HOST, IBKR_PORT, clientId=IBKR_CLIENT_ID)

#         # 2. Use reqScannerDataAsync to wait for the results
#         print("Requesting scanner data...")
#         scan_data = await ib.reqScannerDataAsync(scanner)  
#         results = [
#             {
#                 "rank": d.rank,
#                 "symbol": d.contractDetails.contract.symbol,
#                 "conId": d.contractDetails.contract.conId,
#                 "localSymbol": d.contractDetails.contract.localSymbol,
#                 "tradingClass": d.contractDetails.contract.tradingClass,
#             }
#             for d in scan_data
#         ]
#         df = pd.DataFrame(results)
#         #print(results)
#     except Exception as e:
#         print(f"Error during scan: {e}")
#         df = None
#     finally:
#         # 4. Always disconnect
#         ib.disconnect()         
    
#     return df

def get_report() -> pd.DataFrame:
    with Strategy() as strategy:
        df_scan_data = asyncio.run(get_report_async(strategy))
    
    return df_scan_data 

if __name__ == "__main__":
    df_scan_data = get_report()     # <------- This is the main function that runs the async code and gets the DataFrame

    df_scan_data.to_csv("DATA/1_scan_results.csv", index=False)
    
    #print("-----------------------------------------------------")
    #print(scan_data.subscription)
    #print("-----------------------------------------------------")
    #print(scan_data.scannerSubscriptionOptions)
    #print("-----------------------------------------------------")
