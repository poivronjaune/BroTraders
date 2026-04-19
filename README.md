# BroTraders
Simple IBKR implementation for automated trading. Requires (TWS) Trader WorkStation to be installed. Check config file for correct API Port setup.  
  
Open a terminal and issue the following commands:
  
| COMMAND | DESCRIPTION                                                       | OUTPUT           |
|---------|-------------------------------------------------------------------|------------------|
| report  | Launch a scan report from IBKR to get 50 Gappers (launch at 9:30) | results.json     |
| getdata | Extract data from **results.json** file with minute price data    | many csv files   |
| signals | Generate buy signals from strategy (Morning GAP > 10%)            | buy_signals.json |
| trade   | Place bracket orders (market, stop, profit) for signals produced  | Trades in TWS    |


# Installation  
```
py -3.13 -m venv .venv
.\.venv\Scripts\activate
py -m pip install -U pip
py install -e .

```

### Notes on IBKR Reports  
- The scanCode 'HIGH_OPEN_GAP' returns an empty list before 9:30  
- The scanCode 'TOP_PERC_GAIN' returns Ranks based on current time (even when run after hours)  
