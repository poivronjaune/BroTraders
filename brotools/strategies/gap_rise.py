import pandas as pd
from ib_async import ScannerSubscription

from brotools.strategy_base import BaseStrategy
from brotools.trading_indicators import prev_day_closing_bar, current_day_opening_bar
from brotools.trading_rules import check_trading_window, check_gap_size, check_candles_up

class Strategy(BaseStrategy):
    def __init__(self):
        super().__init__()
        self.name = "Gap Rise Strategy"
        self.description = "Identifies stocks that have a significant price gap up at the market open, followed by green candles."
        self.gap_threshhold = 10

        # --- Live-session window (Eastern time) ---
        # The bot is launched at 09:25 and idles until session_start_time.
        self.session_start_time = "09:30"   # run the scanner at the open
        self.session_end_time   = "09:45"   # gap window closes -> shutdown
        self.entry_cutoff_time  = "09:45"   # no new entries after the window
        self.max_positions      = 3

        # Kept for backwards compatibility with the legacy CLI inspection flow.
        self.active_start_time = "09:30"
        self.active_end_time = "09:45"

        self.rules = [
            (check_trading_window, {"start_time": "09:30", "end_time": "09:45"}),
            (check_gap_size, {"gap_threshold": 10.0}),
            (check_candles_up, {"consecutive": 3})  # Uses 09:30 and 16:00 by default for RTH
        ]

    def scanner(self):
        sub = ScannerSubscription()
        sub.numberOfRows = 50
        sub.instrument   = 'STK'
        sub.locationCode = 'STK.US.MAJOR'
        sub.scanCode    = 'TOP_PERC_GAIN'       # sub.scanCode     = 'HIGH_OPEN_GAP'   

        sub.abovePrice   = 10
        sub.belowPrice   = 200
        sub.aboveVolume  = 100000               # 1 Millions transactions, 100 000 is 100k, 10 000 is 10k
        sub.marketCapAbove = 300                # Small Market Capitalisation and above
        #sub.marketCapBelow = 10000             # Medium Market Capitalisation and below (Excludes large cap that start at 10 000)        

        return sub
    
    def add_indicators(self, df_data):
        # TODO: Evaluate if indicator functions should modify the dataframe or keep it in the function

        prev_close = prev_day_closing_bar(df_data)
        df_data["gap_close_time"] = prev_close.name
        df_data["gap_close_price"] = prev_close["close"] 

        curr_open = current_day_opening_bar(df_data)
        df_data["gap_open_time"] = curr_open.name
        df_data["gap_open_price"] = curr_open["open"]

        df_data["gap_size"] = (df_data["gap_open_price"] - df_data["gap_close_price"]).round(2)
        df_data["gap_percent"] = (df_data["gap_size"] / df_data["gap_close_price"] * 100).round(2)        

        return df_data
    
    def is_buy_signal(self, df_data) -> bool:
        is_buy_signal = False
        
        # Automatically pull the symbol if it exists in the data
        symbol = df_data["symbol"].iloc[0] if "symbol" in df_data.columns else "UNKNOWN"

        # Assume we are trading in the day of our last cande datetime
        # Open Gap > 10%
        # First three bars must be green

        # Setup conditions to fail by default
        conditions_trace = {
            "symbol": symbol,
            "buy_signal": False
        }
        
        all_rules_passed = True

        for rule_func, kwargs in self.rules:
            # Execute the external function and unpack its specific arguments (**kwargs)
            rule_name, passed = rule_func(df_data, **kwargs)
            
            conditions_trace[rule_name] = passed
            
            if not passed:
                all_rules_passed = False # Fail signal on first failed rule
                
        conditions_trace["buy_signal"] = all_rules_passed

        # 2. CAPTURE THE LAST ROW IN THE DATAFRAME to pass in the buy_signals
        last_candle = df_data.iloc[-1]
        last_time = df_data.index.max()

        # Format timestamp cleanly as a string
        if hasattr(last_time, 'strftime'):
            last_time_str = last_time.strftime('%Y-%m-%d %H:%M:%S')
        else:
            last_time_str = str(last_time)

        # Inject the final candle metrics into the tracer payload
        conditions_trace["signal_time"] = last_time_str
        conditions_trace["signal_open"] = float(last_candle["open"])
        conditions_trace["signal_high"] = float(last_candle["high"])
        conditions_trace["signal_low"] = float(last_candle["low"])
        conditions_trace["signal_close"] = float(last_candle["close"])
        conditions_trace["signal_volume"] = int(last_candle["volume"])

        return conditions_trace

    def is_session_done(self) -> bool:
        """The gap window only allows a fixed number of entries. Once the bot
        has emitted ``max_positions`` signals there is nothing left to do, so it
        can shut down early (before ``session_end_time``)."""
        return self._signals_emitted >= self.max_positions