# BroTraders
Simple IBKR implementation for automated trading. Requires Trader WorkStation (TWS) to be installed before runing these scripts. Check config file for correct API Port setup.  
  
Open a terminal and issue the following commands:
  
| COMMAND | DESCRIPTION                                                       | OUTPUT                |
|---------|-------------------------------------------------------------------|-----------------------|
| report  | Launch a scan report from IBKR to get 50 Gappers (launch at 9:30) | results.json          |
| getdata | Extract data from **results.json** file with minute price data    | many csv files        |
| signals | Generate buy signals from strategy (Morning GAP > 10%)            | buy_signals.json      |
| orders  | Place bracket orders (market, stop, profit) for signals produced  | submitted_orders.json |


# Installation  
```
py -3.12 -m venv .venv
.\.venv\Scripts\activate
py -m pip install -U pip
py install -e .

```
or use the helper powerahell script that runs all install commands:
```
install.ps1
```

### Notes on IBKR Reports  
- The scanCode 'HIGH_OPEN_GAP' returns an empty list before 9:30  
- The scanCode 'TOP_PERC_GAIN' returns Ranks based on current time (even when run after hours)  
