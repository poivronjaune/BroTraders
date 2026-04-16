import sys
import pandas as pd
import json
from datetime import datetime
from ib_async import *
from brotools.config import IBKR_HOST, IBKR_PORT, IBKR_CLIENT_ID
from brotools.strat_gap_rise import strategy


def load_tickers():
    with open('DATA/results.json', 'r') as f:
        symbols = json.load(f)
        
    tickers = [t['symbol'] for t in symbols]
    
    return tickers

def getdata():
    ib = IB()
    ib.connect(IBKR_HOST, IBKR_PORT, clientId=IBKR_CLIENT_ID)

    tickers = load_tickers()
    for ticker in tickers:
        contract = Stock(ticker, "SMART", "USD")                    # Step 1 : Define a contract object for which to fetch data (stocks in this case)
        
        bars = ib.reqHistoricalData(                                # Step 2 : request historical data for the last day in 1 minute bars (limitations apply, 1 minute => about 1 month)
            contract,
            endDateTime="",
            durationStr="2 D",
            barSizeSetting="1 min",
            whatToShow="TRADES",
            useRTH=False                                            # When useRTH is False, get Extended Hours and PreMarket data
        )    

        #print(bars)
        df = util.df(bars)
        df.to_csv(f"DATA/{contract.symbol}_1min_{datetime.now().strftime('%Y%m%d_%H%M')}.csv", index=False)

    ib.disconnect()
    

def getreport():
    ib = IB()
    ib.connect(IBKR_HOST, IBKR_PORT, clientId=IBKR_CLIENT_ID)

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
    sub.numberOfRows   = 50
    sub.instrument     = 'STK'
    sub.locationCode   = 'STK.NASDAQ'
    #sub.scanCode       = 'TOP_PERC_GAIN'
    sub.scanCode       = 'HIGH_OPEN_GAP'
    sub.abovePrice     = 20
    sub.belowPrice     = 1000
    #sub.aboveVolume    = 1000000    # 1 Millions transactions
    #sub.marketCapAbove = 300        # Small Market Capitalisation and above
    #sub.marketCapBelow = 10000      # Medium Market Capitalisation and below (Excludes large cap that start at 10 000)

    scanData = ib.reqScannerData(sub)    

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

    with open('DATA/results.json', 'w') as f:
        json.dump(results, f, indent=4)
    #print(json.dumps(results, indent=4))
    # for scan in results:
    #     print(scan)

    ib.disconnect()


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
        df = pd.read_csv(f'DATA/{prospect}_1min_20260416_1531.csv')
        # TODO: Add error handling
        buy_signal = strategy(prospect, df, gap_threshold=10.0)
        
        if buy_signal is None:
            continue
        
        buy_signals.append(buy_signal)

    for signal in buy_signals:
        print(f"Buy Signal: {signal['symbol']} - Gap: {signal['gap']:.2f}, Gap Percentage: {signal['gap_perc']:.2f}%")
    

def main():
    print("Hello, BroTools!")
    print("This is the main entry point of the application.")
    # You can add more functionality here as needed.
    
if __name__ == "__main__":
    main()
    