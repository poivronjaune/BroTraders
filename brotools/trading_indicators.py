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


def prev_day_high_low(df_prices: pd.DataFrame, open_time="09:30", close_time="16:00"):
    """Return the previous trading day's regular-session (high, low) as floats.

    Mirrors ProRealTime ``DHigh(1)`` / ``DLow(1)`` using only the regular
    session (``open_time``–``close_time``) of the single most recent day that
    precedes the last day present in ``df_prices``.
    """
    last_day = df_prices.index.date.max()
    prev_days_df = df_prices[df_prices.index.date < last_day]
    if prev_days_df.empty:
        raise ValueError("No historical data available prior to the last trading day.")

    regular_hours_df = prev_days_df.between_time(open_time, close_time)
    if regular_hours_df.empty:
        raise ValueError(f"No regular session data found ({open_time} to {close_time}) on previous days.")

    prev_day = regular_hours_df.index.date.max()
    prev_day_df = regular_hours_df[regular_hours_df.index.date == prev_day]
    return float(prev_day_df["high"].max()), float(prev_day_df["low"].min())