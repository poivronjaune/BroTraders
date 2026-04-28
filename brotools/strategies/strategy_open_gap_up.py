import os
import json 
import pandas as pd 
from datetime import datetime, time
from ib_async import ScannerSubscription

from brotools import to_serializable
from brotools.services import ibkr_subscription_async, ibkr_get_price_data

# TODO: Improve this class organisation (it is a little hacky!)
# Important use PascalCase for class Strategy Name and snake_case for module file name 
class StrategyOpenGapUp:
    """Detects a significant gap-up buy signal based on prior close and early candle confirmation.

    This strategy compares the previous day's closing price against a user-defined
    reference time on the current day, acting as a flexible "open" price. This design
    allows the strategy to be evaluated pre-market, at the open, or at any point during
    the trading session.

    A buy signal is triggered when two conditions are met:
        1. The price at the reference time is at least 10% above the previous day's close
           (gap-up condition).
        2. The next consecutive candles following the reference time are all green
           (close > open), confirming upward momentum.

    Attributes:
        gap_threshold (float): Minimum required gap as a decimal fraction. Defaults to 0.10 (10%).
        reference_time (str): The time on the current day used as the proxy open,
            in "HH:MM" format (e.g., "09:30" for market open, "04:00" for pre-market).
        up_trend_window (int): Number of candles to check trend direction after reference_time

    Example:
        strategy = GapUpStrategy(gap_percentage="10.0", reference_time="09:30", up_trend_window=3)
    """

    def __init__(self, gap_percentage="10.0", reference_time="09:30", up_trend_window=3):
        self.name = "Open Gap Strategy"
        self.ticker_source = "IBKR_Subscription"
        
        self.gap_threshold = gap_percentage
        self.up_trend_window = up_trend_window
        self.reference_time = datetime.strptime(reference_time, "%H:%M").time() 
        self.historical_data_window = '5 D'   

    @property
    def subscription(self):
        # Define the subscription object directly in strategy
        return ScannerSubscription(
            numberOfRows=5,
            instrument='STK',
            #locationCode='STK.US.MAJOR',
            locationCode='STK.NASDAQ',
            scanCode='HIGH_OPEN_GAP',
            abovePrice=2,
            belowPrice=500,
            aboveVolume=100000,
            marketCapAbove=300
        )

    async def prospects(self, ib):
        print(f"Requesting scanner data for: {self.name}")
        prospects = await ibkr_subscription_async(ib, self.subscription)
        return prospects

    async def get_prices(self, ib, ticker):
        df_prices = await ibkr_get_price_data(ib, ticker, back_days=self.up_trend_window) # Data stored on disk
        return df_prices

    # Utility functions specific to this strategy
    def _get_prev_close(self, df):
        try:
            df = df.copy()
            df['date'] = pd.to_datetime(df['date'], utc=True).dt.tz_localize(None)
            
            date_curr = df['date'].iloc[-1].date()
            date_prev = df['date'][df['date'].dt.date < date_curr].iloc[-1].date()

            df_prev = df[df['date'].dt.date == date_prev]
            df_prev = df_prev[df_prev['date'].dt.hour < 16]

            return df_prev['close'].iloc[-1], date_prev
        except Exception as e:
            return None, None    
    
    def _get_currday_open(self, df):    
        try:
            df = df.copy()
            df['date'] = pd.to_datetime(df['date'], utc=True).dt.tz_localize(None)

            date_curr = df['date'].iloc[-1].date()
            df1 = df[df['date'].dt.date == date_curr]

            df_ref = df1[df1['date'].dt.time == self.reference_time]

            if df_ref.empty:
                return None, None

            return df_ref['open'].iloc[0], date_curr
        except Exception as e:
            return None, None    
   
    
    
    def _get_gap(self, close_price, open_price, gap_threshold):
        gap = open_price - close_price
        gap_perc = gap / close_price * 100
        return {
            "gap": gap,
            "gap_perc": gap_perc,
            "gap_threshold": gap_threshold,
            "threshold_reached": gap_perc >= gap_threshold
        }

    def _get_uptrend(self, df, date_curr):
        try:
            df = df.copy()
            df['date'] = pd.to_datetime(df['date'], utc=True).dt.tz_localize(None)

            df_curr = df[df['date'].dt.date == date_curr]
            df_after = df_curr[df_curr['date'].dt.time > self.reference_time].head(self.up_trend_window)
            
            if len(df_after) < self.up_trend_window:
                return {"candles": [], "up_trend": False}

            candles = [
                {
                    "date": row['date'].strftime('%Y-%m-%d %H:%M:%S'),
                    "open": row['open'],
                    "close": row['close'],
                    "direction": "up" if row['close'] > row['open'] else "down"
                }
                for _, row in df_after.iterrows()
            ]

            return {
                "candles": candles,
                "up_trend": all(c["direction"] == "up" for c in candles)
            }
        except Exception as e:
            return {"candles": [], "up_trend": False}


    def signals(self, prospect, df, gap_threshold=10.0):
        close_price, date_prev = self._get_prev_close(df)
        open_price, date_curr = self._get_currday_open(df)

        if close_price is None or open_price is None:
            print(f"{prospect} -> Skipped, no Analysis possible, not enough data [ Close:{close_price}, Open:{open_price} ].")
            return None

        gap_analysis = self._get_gap(close_price, open_price, gap_threshold)
        uptrend_analysis = self._get_uptrend(df, date_curr)

        buy_signal = {
            "symbol": prospect,
            "date_prev": date_prev.strftime('%Y-%m-%d %H:%M:%S'),
            "close_prev": close_price,
            "date_curr": date_curr.strftime('%Y-%m-%d %H:%M:%S'),
            "open_curr": open_price,
            **gap_analysis,
            **uptrend_analysis
        }
        print(f'{buy_signal["symbol"]} -> Previous Close: {buy_signal["close_prev"]}, Current Open: {buy_signal["open_curr"]}, GAP: {buy_signal["gap_perc"]:.2f}% --- {len(df)} rows Analysed')

        return to_serializable(buy_signal)
    
    
    
    
       