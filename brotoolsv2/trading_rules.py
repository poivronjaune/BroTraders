import logging 

logger = logging.getLogger(__name__)

def check_trading_window(df_data, start_time="09:30", end_time="10:00"):
    """Validates if the last candle is within the specified time window."""
    last_candle_time = df_data.index.max()
    current_time_str = last_candle_time.strftime("%H:%M")
    
    is_valid = start_time <= current_time_str <= end_time
    
    # return "rule_condition", boolen_value
    return "valid_trading_window", is_valid


def check_gap_size(df_data, gap_threshold=10.0):
    """Validates if the opening gap is above the threshold percentage."""
    # Assuming df_data or a helper calculates this
    # (Using mock extraction for the example structural flow)
    gap_percent = df_data["gap_percent"].iloc[-1] if "gap_percent" in df_data.columns else 0.0
    
    is_valid = gap_percent > gap_threshold
    
    # return "rule_condition", boolen_value
    return "gap_threshold_reached", is_valid

def check_candles_up(df_data, consecutive=3, start_rth="09:30", end_rth="16:00"):
    """
    Filters data for the most recent day, strips out pre-market and 
    after-hours data based on start_rth and end_rth parameters, 
    verifies the session opening bar, and checks if the subsequent 
    N consecutive candles are green.
    """ 

    rule_name = f"{consecutive}_candles_up"  

    # 1. Isolate the data for the most recent day in the dataset
    most_recent_date = df_data.index.max().date()
    df_day = df_data[df_data.index.date == most_recent_date]  

    # 2. Filter out pre/post market data using the default parameters
    df_regular_hours = df_day.between_time(start_rth, end_rth)
    
    # 3. Safety check: Do we have enough candles during regular hours?
    if len(df_regular_hours) <= consecutive:
        return rule_name, False
    
    # 4. Double-check that our first regular hours bar matches our start_rth time
    opening_bar_time = df_regular_hours.index[0].strftime("%H:%M")
    if opening_bar_time != start_rth:
        logger.warning(f"⚠️  RTH opening bar time mismatch: Expected {start_rth}, but got {opening_bar_time} for {most_recent_date}. This may indicate missing pre-market data or a data quality issue.")
        return rule_name, False
    
    # 5. Slice the consecutive candles immediately AFTER the opening bar
    post_open_candles = df_regular_hours.iloc[1 : 1 + consecutive]

    # 6. Check if Close > Open for all candles in this window
    are_candles_green = post_open_candles["close"] > post_open_candles["open"]
    is_valid = are_candles_green.all()

    return rule_name, bool(is_valid)


