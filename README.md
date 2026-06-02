# BroTraders
Simple IBKR implementation for automated trading. Requires Trader WorkStation (TWS) to be installed before runing these scripts. Check config file for correct API Port setup and default strategy. Works with command lines on the market open. Run the scripts around 9:33.  
  
Open a terminal and issue the following commands:
  
| COMMAND    | DESCRIPTION                                                       | OUTPUT                |
|----------- |-------------------------------------------------------------------|-----------------------|
| scan       | Launch a scan report from IBKR to get 50 Gappers (launch at 9:30) | 1_scan_results.csv    |
| getdata    | Extract price data for symbols in scan result file                | ticker.csv files      |
| indicators | Generate indicators from strategy (adding columsn to price data)  | ticker.csv files      |
| signals    | Generate buy signals from strategy (Morning GAP > 10%)            | 2_buy_signals.json    |
| orders     | Place bracket orders (market, stop, profit) for signals produced  | 3_placed_orders.json  |
  
Then track stop loss and profit target execution directly in Trader Worksation.     

# Installation  
```
py -3.12 -m venv .venv
.\.venv\Scripts\activate
py -m pip install -U pip
py install -e .

```

### Notes on IBKR Reports
The Strategy class uses an IBKR subscription for scanner reports. Some scan_code are listed below.  
  
- The scanCode 'HIGH_OPEN_GAP' returns an empty list before 9:30  
- The scanCode 'TOP_PERC_GAIN' returns Ranks based on current time (even when run after hours)   

Example of scanner subscription defintion:
```        
sub = ScannerSubscription()
sub.numberOfRows = 50
sub.instrument   = 'STK'
sub.locationCode = 'STK.US.MAJOR'
sub.scanCode     = 'TOP_PERC_GAIN'

sub.abovePrice   = 10                   # Last price must be above 10$
sub.belowPrice   = 200                  # Last price must be below 200$
sub.aboveVolume  = 100000               # Volume of trades must be above 100 000 transactions
sub.marketCapAbove = 300                # Market Capitaisation must be above 300 (Small Market Capitalisation)
#sub.marketCapBelow = 10000             # Market Capitaisation must be below Capitalisation and below
```        

Some values for MarketCap:
| Tier  | marketCapAbove    | marketCapBelow     | Notes        |
|-------|-------------------|--------------------|--------------|
| Nano  | 0                 | 50                 | Under $50M   |
| Micro | 50                | 300                | $50M–$300M   |
| Small | 300               | 2_000              | $300M–$2B    |
| Mid   | 2_000             | 10_000             | $2B–$10B     |
| Large | 10_000            | 200_000            | $10B–$200B   |
| Mega  | 200_000           | None               | $200B+       |

