import pandas as pd
import asyncio
from datetime import datetime

from ib_async import IB, Stock, util, MarketOrder, LimitOrder, StopOrder

from brotools.config import IBKR_HOST, IBKR_PORT, IBKR_CLIENT_ID
from brotools.strategies.gap_rise import Strategy

async def get_report_async(strategy: Strategy) -> pd.DataFrame | None:
    ib = IB()
    df = None

    try:
        # Get the strategy class and obtain a scanner object
        #strategy = Strategy()
        scanner = strategy.scanner()

        # 0. Use connectAsync
        await ib.connectAsync(IBKR_HOST, IBKR_PORT, clientId=IBKR_CLIENT_ID)
        
        # 1. Use reqScannerDataAsync to wait for the results
        print("Requesting scanner data...")
        scan_data = await ib.reqScannerDataAsync(scanner)  

        #2. Extract relevant info into a list of dicts, then create a DataFrame
        results = [
            {
                "rank": d.rank,
                "symbol": d.contractDetails.contract.symbol,
                "conId": d.contractDetails.contract.conId,
                "localSymbol": d.contractDetails.contract.localSymbol,
                "tradingClass": d.contractDetails.contract.tradingClass,
            }
            for d in scan_data
        ]
        df = pd.DataFrame(results)
    except Exception as e:
        print(f"Error during scan: {e}")
    finally:
        # 4. Always disconnect
        ib.disconnect() 

    return df

async def save_data_async(tickers, timeframe= None, back_days=None):
    ib = IB()
    try:
        # 1. Connect ONCE using the async method
        await ib.connectAsync(IBKR_HOST, IBKR_PORT, clientId=IBKR_CLIENT_ID)
        print(f"Get Data Started")
        
        for ticker in tickers:
            # Check if ticker is a conId (int) or symbol (str)
            if isinstance(ticker, int):
                contract = Stock(conId=ticker)
            else:
                contract = Stock(ticker, "SMART", "USD")

            # 2. Qualify the contract to ensure we have the right details
            await ib.qualifyContractsAsync(contract)
            print(f"Fetching data for {contract.symbol}...")

            # 3. Use the Async version of historical data request
            bars = await ib.reqHistoricalDataAsync(
                contract,
                endDateTime="",
                durationStr="2 D",
                barSizeSetting="1 min",
                whatToShow="TRADES",
                useRTH=False  # Crucial for Gaps: gets Pre-Market data
            )

            if bars:
                df = util.df(bars)
                df['symbol'] = contract.symbol
                #filename = f"DATA/{contract.symbol}_1min_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
                filename = f"DATA/{contract.symbol}.csv"
                df.to_csv(filename, index=False)
                print(f"Saved {len(bars)} rows to {filename}")
            else:
                print(f"No data returned for {contract.symbol}")

            # 4. Small sleep to avoid hitting IBKR pacing violations
            await asyncio.sleep(0.1)            
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        # 5. Always disconnect in the finally block
        ib.disconnect()             

def create_bracket_order(qte = 1, estimated_buy_price = 100):
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

def build_buy_orders(df_signals: pd.DataFrame) -> list[dict]:
    """Pure sync. Build contracts and bracket orders — no IB, no async."""
    orders = []
    for _, signal in df_signals.iterrows():
        contract = Stock(signal['symbol'], 'SMART', 'USD')
        estimated_price = round(signal['signal_close'], 2)
        parent, stop_loss, take_profit = create_bracket_order(1, estimated_price)
        orders.append({
            "symbol": signal['symbol'],
            "contract": contract,
            "parent": parent,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
        })
    return orders

async def place_order_async(ib: IB, item: dict) -> dict:
    """Async. One symbol: qualify, place bracket, yield for TWS ack."""
    contract = item['contract']
    parent   = item['parent']
    sl       = item['stop_loss']
    tp       = item['take_profit']

    await ib.qualifyContractsAsync(contract)

    parent_trade = ib.placeOrder(contract, parent)
    await asyncio.sleep(0)          # yield → TWS assigns orderId

    sl.parentId = parent.orderId
    tp.parentId = parent.orderId

    sl_trade = ib.placeOrder(contract, sl)
    tp_trade = ib.placeOrder(contract, tp)
    await asyncio.sleep(0)          # yield → TWS acks children

    print(f"✅ {item['symbol']} submitted (Parent ID: {parent.orderId})")

    return {
        "symbol":       item['symbol'],
        "parent_trade": parent_trade,
        "sl_trade":     sl_trade,
        "tp_trade":     tp_trade,
    }

async def place_orders_async():
    df_signals = pd.read_csv('DATA/2_buy_signals.csv', index_col='rank')    
    df_signals = df_signals[df_signals['buy_signal'] == True]
    
    if df_signals.empty:
        print("⚠️  No buy signals detected. Order placement skipped.\n")
        return

    order_items = build_buy_orders(df_signals)
    print(f"📋 {len(order_items)} signals prepared, connecting to IB...")

    parent, stop_loss, take_profit =create_bracket_order()
    print(parent)
    print(stop_loss)
    print(take_profit)
    print(df_signals)

    ib = IB()
    placed_orders = []
    try:
        await ib.connectAsync(IBKR_HOST, IBKR_PORT, clientId=IBKR_CLIENT_ID)

        for item in order_items:
            try:
                result = await place_order_async(ib, item)
                placed_orders.append(result)
            except Exception as e:
                print(f"❌ {item['symbol']} failed: {e}")

        # Wait for all parents to reach a stable status before saving
        for result in placed_orders:
            trade = result['parent_trade']
            while trade.orderStatus.status not in ('PreSubmitted', 'Submitted', 'Filled'):
                await asyncio.sleep(0.1)

    finally:
        ib.disconnect()
        if placed_orders:
            rows = []
            for result in placed_orders:
                rows.append({
                    "symbol":           result['symbol'],
                    "submitted_time":   datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    "parent_order_id":  result['parent_trade'].order.orderId,
                    "parent_status":    result['parent_trade'].orderStatus.status,
                    "sl_order_id":      result['sl_trade'].order.orderId,
                    "sl_status":        result['sl_trade'].orderStatus.status,
                    "tp_order_id":      result['tp_trade'].order.orderId,
                    "tp_status":        result['tp_trade'].orderStatus.status,
                })
            pd.DataFrame(rows).to_csv('DATA/3_placed_orders.csv', index=False)
