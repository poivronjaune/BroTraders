import pandas as pd
from ib_async import ScannerSubscription  

class Strategy:
    def __init__(self):
        self.name = "Gap Rise Strategy"
        self.description = "Identifies stocks that have a significant price gap up at the market open, followed by green candles."

    def __enter__(self):
        # This runs when entering the 'with' block
        print(f"Opening connection to {self.name}.")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # This ALWAYS runs when leaving the 'with' block
        print(f"Closing connection to {self.name} safely.")
        # Return False to let any exceptions propagate normally

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
        # Placeholder for future indicator calculations
        prev_close = self.prev_day_close_bar(df_data)
        df_data["gap_close_time"] = prev_close.name
        df_data["gap_close_price"] = prev_close["close"] 

        curr_open = self.current_day_open_bar(df_data)
        df_data["gap_open_time"] = curr_open.name
        df_data["gap_open_price"] = curr_open["open"]

        df_data["gap_size"] = (df_data["gap_open_price"] - df_data["gap_close_price"]).round(2)
        df_data["gap_percent"] = (df_data["gap_size"] / df_data["gap_close_price"] * 100).round(2)        

        return df_data
    
    def add_signal(self, df_data):
        # Placeholder for future signal generation logic
        df_data['new_col'] = 100
        return df_data
    
    #
    # UTILITY FUNCTIONS FOR STRATEGY LOGIC
    #
    def prev_day_close_bar(self, df_prices: pd.DataFrame):
        last_day = df_prices.index.date.max()
        prev_days_df = df_prices[df_prices.index.date < last_day]
        
        if prev_days_df.empty:
            raise ValueError("No historical data available prior to the last trading day.")
        
        regular_hours_df = prev_days_df.between_time("09:30", "16:00")
        if regular_hours_df.empty:
            raise ValueError("No regular session data found (09:30 to 16:00) on previous days.")        
        
        return regular_hours_df.iloc[-1]
    
    def current_day_open_bar(self, df_prices: pd.DataFrame):
        last_day = df_prices.index.date.max()
        current_day_df = df_prices[df_prices.index.date == last_day]
        regular_hours_df = current_day_df.between_time("09:30", "16:00")

        if regular_hours_df.empty:
            raise ValueError(f"No regular session data found (09:30 to 16:00) for the current day ({last_day}).")        
        
        return regular_hours_df.iloc[0]