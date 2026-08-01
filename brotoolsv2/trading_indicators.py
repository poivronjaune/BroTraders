import logging
import pandas as pd
from datetime import time

logger = logging.getLogger(__name__)

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

def compute_session_vwap(df_prices: pd.DataFrame, start_time="09:30", end_time="16:00"):
    """
    Computes cumulative Volume-Weighted Average Price using typical price
    (High+Low+Close)/3, accumulated only over bars within [start_time, end_time]
    on the most recent day in df_prices. VWAP resets at start_time.

    Returns a pd.Series aligned to df_prices.index; values outside the
    window (or on earlier days) are NaN.
    """
    last_day = df_prices.index.date.max()
    df_day = df_prices[df_prices.index.date == last_day]
    df_window = df_day.between_time(start_time, end_time)

    if df_window.empty:
        return pd.Series(index=df_prices.index, dtype="float64")

    typical_price = (df_window["high"] + df_window["low"] + df_window["close"]) / 3
    cum_pv = (typical_price * df_window["volume"]).cumsum()
    cum_vol = df_window["volume"].cumsum()
    vwap = cum_pv / cum_vol

    return vwap.reindex(df_prices.index)    