import json
import pandas as pd
from datetime import datetime, time


def get_prev_close(df):
    try:    
        date_prev = pd.to_datetime(df['date'].iloc[0]).date()
        df_filtered = pd.to_datetime(df['date']).dt.date == date_prev
        df1 = df[df_filtered]
        df_prev = df1[pd.to_datetime(df1['date']).dt.hour < 16]
        return df_prev['close'].iloc[-1], date_prev
    except Exception as e:
        return None, None
    

def get_currday_open(df):    
    now = datetime.now().time()
    market_open_time = time(9, 30)
    
    try:
        date_curr = pd.to_datetime(df['date'].iloc[-1]).date()
        df_filtered = pd.to_datetime(df['date']).dt.date == date_curr
        df1 = df[df_filtered]
        
        if now < market_open_time:
            # If pre-market return latest candle retrieved
            return df1['open'].iloc[-1], date_curr
        
        df_curr = df1[pd.to_datetime(df1['date']).dt.hour >= 9]
        df_curr = df_curr[pd.to_datetime(df_curr['date']).dt.hour < 10]
        # take rows greater than 9:30 
        df_curr = df_curr[pd.to_datetime(df_curr['date']).dt.minute >= 30]

        return df_curr['open'].iloc[0], date_curr
    except Exception as e:
        return None, None

    
def strategy(prospect,df, gap_threshold=10.0):
    buy_signal = None 
    close_price, date_prev = get_prev_close(df)
    open_price, date_curr = get_currday_open(df)
    
    # Sanity Checks
    if close_price is None or open_price is None:
        print(f"{prospect} -> Skipped, no Analysis possible, not enough data [ Close:{close_price}, Open:{open_price} ].")
        return None
    

    gap = open_price - close_price
    gap_perc = gap / close_price * 100
    if gap_perc >= gap_threshold:
        is_treshhold_reached = True
    else:        
        is_treshhold_reached = False


    buy_signal = {
        "symbol": prospect,
        "gap": gap,
        "gap_perc": gap_perc,
        "gap_treshold": gap_threshold,
        "date_prev": date_prev.strftime('%Y-%m-%d %H:%M:%S'),
        "close_prev": close_price,
        "date_curr": date_curr.strftime('%Y-%m-%d %H:%M:%S'),
        "open_curr": open_price,
        "threshold_reached": is_treshhold_reached
    }
    print(f'{buy_signal["symbol"]} -> Previous Close: {buy_signal["close_prev"]}, Current Open: {buy_signal["open_curr"]}, GAP: {buy_signal["gap_perc"]:.2f}% --- {len(df)} rows Analysed')    

    return buy_signal


    