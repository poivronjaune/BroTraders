import pandas as pd

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
    try:
        date_curr = pd.to_datetime(df['date'].iloc[-1]).date()
        df_filtered = pd.to_datetime(df['date']).dt.date == date_curr
        df1 = df[df_filtered]
        df_curr = df1[pd.to_datetime(df1['date']).dt.hour >= 9]
        # df_curr = df_curr[pd.to_datetime(df_curr['date']).dt.hour < 10]
        # take rows greater than 9:30 
        df_curr = df_curr[pd.to_datetime(df_curr['date']).dt.minute >= 30]

        return  df_curr['open'].iloc[-1], date_curr
        #return df_curr['open'].iloc[0], date_curr
    except Exception as e:
        return None, None

    
def strategy(prospect,df, gap_threshold=10.0):
    buy_signal = None 
    close_price, date_prev = get_prev_close(df)
    open_price, date_curr = get_currday_open(df)
    
    # Sanity Checks
    if close_price is None or open_price is None:
        return None
    

    gap = open_price - close_price
    gap_perc = gap / close_price * 100
    # print(f"Gap: {gap:.2f}, Gap Percentage: {gap_perc:.2f}%")
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

    return buy_signal