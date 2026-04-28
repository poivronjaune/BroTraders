import json
import asyncio
import pandas as pd
from datetime import datetime

from ib_async import Stock, util, MarketOrder, LimitOrder, StopOrder

# TODO: Remove HARD CODED DATA folder and names

async def ibkr_subscription_async(ib, subscription_parameters):
    try:
        scanData = await ib.reqScannerDataAsync(subscription_parameters)

        contract_details = []
        for d in scanData:
            contract = d.contractDetails.contract
            details = await ib.reqContractDetailsAsync(contract) 
            full_details = details[0] if details else None              

            contract_details.append({
                "rank": d.rank,
                "conId": contract.conId,
                "symbol": contract.symbol,
                "localSymbol": contract.localSymbol,
                "tradingClass": contract.tradingClass,
                "primaryExchange": contract.primaryExchange,
                "currency": contract.currency,
                "longName": full_details.longName if full_details else "",
                "industry": full_details.industry if full_details else "",
                "tradingHours": full_details.tradingHours if full_details else "",
            })
       
        # 3. Save to file
        #with open('DATA/prospects.json', 'w') as f:
        #    json.dump(contract_details, f, indent=4)
        
        print(f"Success: {len(contract_details)} items saved to DATA/prospects.json")
        return contract_details
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
        await asyncio.sleep(0.1)  
        if bars:
            df = util.df(bars)
            df["date"] = pd.to_datetime(df["date"], utc=True)
            #min_row = df.loc[df["date"].idxmin(), "date"]
            #max_row = df.loc[df["date"].idxmax(), "date"]
                        
            # folder = "DATA/"
            # fname = f"{contract.symbol}_1min_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
            # filename = folder + fname
            # df.to_csv(filename, index=False)
            # print(f"Saved {len(bars)} rows to {filename}")
            
            return df
            #return {
            #    "price_data": df,
            #    #"fname":    fname,
            #    "min_date": min_row.strftime("%Y-%m-%d"),
            #    "min_time": min_row.timetz(),
            #    "max_date": max_row.strftime("%Y-%m-%d"),
            #    "max_time": max_row.timetz(),
            #}
        else:
            print(f"No data returned for {contract.symbol}")        
            return None
        
    except Exception as e:
        print(f"ERROR Laoding Price Data from IBKR")
        return None

async def ibkr_create_bracket_order(qte, estimated_buy_price):
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