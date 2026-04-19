# BroTraders
Simple IBKR implementation for automated trading

# Installation  
Install IBAPI from IBKR
pip install ibapi from installed folder


### Notes on IBKR Reports  
The scanCode 'HIGH_OPEN_GAP' return an empty list before 9:30  

The scanCode 'TOP_PERC_GAIN' returns Ranks based on current time (even when run after hours)  



# Understanding Lingo  
## Buy or Sell Orders  
#### Market Buy
When you place a market order you are explicitly stating that you want to buy (or sell) immediately, regardless of the price.  
Instead of a single "market price," you need to think of it as two separate doors:  
**The Bid**: What buyers are willing to pay.
**The Ask**: What sellers are willing to accept.

The difference between the ASK and BID is called the spread.  

A market order effectively "crosses the spread." If you are buying, your broker will match you with the lowest available Ask price on the order book.  
If that seller only has half the shares you need, the broker moves to the next cheapest seller until your order is filled.  
This is why market orders are great for speed but can be risky in volatile markets where the price might jump significantly between the time you click "buy" and the time the trade executes.

So when placing a MarketOrder, only the pass the buy action and the qunatity as parameters

```
parent = MarketOrder('BUY', 1)
```

#### Limit Buy 
