import pandas as pd
from datetime import time

def prev_day_closing_bar(df_prices: pd.DataFrame, open_time="09:30", close_time="16:00"):
    last_day = df_prices.index.date.max()
    prev_days_df = df_prices[df_prices.index.date < last_day]
    
    if prev_days_df.empty:
        raise ValueError("No historical data available prior to the last trading day.")
    
    regular_hours_df = prev_days_df.between_time(open_time, close_time)
    if regular_hours_df.empty:
        raise ValueError(f"No regular session data found ({open_time} to {close_time}) on previous days.")        
    
    return regular_hours_df.iloc[-1]

def current_day_opening_bar(df_prices: pd.DataFrame,open_time="09:30", close_time="16:00"):
    last_day = df_prices.index.date.max()
    current_day_df = df_prices[df_prices.index.date == last_day]
    regular_hours_df = current_day_df.between_time(open_time, close_time)

    if regular_hours_df.empty:
        raise ValueError(f"No regular session data found ({open_time} to {close_time}) for the current day ({last_day}).")        
    
    return regular_hours_df.iloc[0]