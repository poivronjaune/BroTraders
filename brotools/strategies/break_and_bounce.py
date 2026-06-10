"""
break_and_bounce.py

Break and Bounce strategy (long-only adaptation) for the event-driven bot.

Logic (per the ``Strategies/break_and_bounce.md`` specification):

    Breakout -> Retest -> Confirmation -> Entry

1. Reference levels: previous trading day's regular-session high / low
   (``prevHigh`` / ``prevLow``).
2. Direction (15-minute timeframe): once a 15-minute bar *closes* above
   ``prevHigh`` the bias is set long (``dir = +1``) and stays sticky for the
   rest of the day.
3. Retest + confirmation (5-minute execution bars): a long entry triggers when
   the current 5-minute bar retests ``prevHigh`` (``Low <= prevHigh`` and
   ``Close > prevHigh``) and prints a bullish ``hammer`` or ``bullEngulf``
   candle.
4. Bracket: market entry, 1 contract,
       ``stop   = prevHigh - range * 0.2``
       ``risk   = close - stop``
       ``target = close + risk * 3``

Trading window: 09:30–12:00 (the strategy file's "first 150 minutes"). After
12:00 the bot stops opening new positions but keeps existing positions open
(``close_on_session_end = False``; GTC brackets manage the exit). The short
side of the original specification is intentionally omitted for now.
"""

import pandas as pd
from ib_async import ScannerSubscription

from brotools.strategy_base import BaseStrategy
from brotools.trade_signal import Signal
from brotools.trading_indicators import prev_day_high_low


class Strategy(BaseStrategy):
    def __init__(self):
        super().__init__()
        self.name = "Break and Bounce Strategy"
        self.description = (
            "Previous-day breakout on the 15m, retest of the broken high on the "
            "5m with a bullish reversal candle; long-only, risk:reward 1:3."
        )

        # --- Live-session window (Eastern time) ---
        # "First 150 minutes of the session" -> 09:30 to 12:00.
        self.session_start_time = "09:30"   # run the scanner at the open
        self.session_end_time   = "16:00"   # bot stays up to manage open positions
        self.entry_cutoff_time  = "12:00"   # no new entries after 150 minutes
        self.max_positions      = 3
        self.close_on_session_end = False   # keep positions open after the window

        # --- Data feed ---
        self.bar_size = "5 mins"            # execution chart is 5 minutes

        # Risk on this strategy is candle-range driven, not percentage based.
        self.default_quantity = 1

    # ------------------------------------------------------------------
    # Phase 2 — scanner
    # ------------------------------------------------------------------
    def scanner(self) -> ScannerSubscription:
        sub = ScannerSubscription()
        sub.numberOfRows  = 50
        sub.instrument    = "STK"
        sub.locationCode  = "STK.US.MAJOR"
        sub.scanCode      = "MOST_ACTIVE"
        sub.abovePrice    = 2            # price above $2
        sub.belowPrice    = 250          # price under $250
        sub.marketCapAbove = 300         # small cap and above ($300M)
        return sub

    # ------------------------------------------------------------------
    # Phase 3/4 — indicators
    # ------------------------------------------------------------------
    def add_indicators(self, df_data: pd.DataFrame) -> pd.DataFrame:
        df = df_data

        # Previous-day reference levels (regular session only).
        prev_high, prev_low = prev_day_high_low(df)
        df["prev_high"] = prev_high
        df["prev_low"] = prev_low

        # Candle structure (5-minute execution bars).
        oc_max = df[["open", "close"]].max(axis=1)
        oc_min = df[["open", "close"]].min(axis=1)
        df["body"] = (df["close"] - df["open"]).abs()
        df["range"] = df["high"] - df["low"]
        df["upper_wick"] = df["high"] - oc_max
        df["lower_wick"] = oc_min - df["low"]

        # Bullish reversal patterns.
        df["hammer"] = (df["lower_wick"] > df["body"] * 2) & (df["upper_wick"] < df["body"])
        df["bull_engulf"] = (
            (df["close"] > df["open"])
            & (df["close"] > df["high"].shift(1))
            & (df["open"] < df["low"].shift(1))
        )

        # Retest of the broken previous-day high.
        df["retest_long"] = (df["low"] <= prev_high) & (df["close"] > prev_high)

        # 15-minute sticky long bias (today only).
        df["dir_long"] = self._compute_dir_long(df, prev_high)

        return df

    @staticmethod
    def _compute_dir_long(df: pd.DataFrame, prev_high: float) -> pd.Series:
        """Long bias becomes True once a 15-minute RTH bar closes > prevHigh."""
        result = pd.Series(False, index=df.index)

        last_day = df.index.max().date()
        today = df[df.index.date == last_day]
        if today.empty:
            return result

        rth = today.between_time("09:30", "16:00")
        if rth.empty:
            return result

        bars15 = (
            rth.resample("15min")
            .agg({"open": "first", "high": "max", "low": "min", "close": "last"})
            .dropna()
        )
        breakout = bars15["close"] > prev_high
        if not breakout.any():
            return result

        # First 15m bar that breaks out; bias is valid from that bar's close.
        first_break_start = breakout.idxmax()
        break_close_time = first_break_start + pd.Timedelta(minutes=15)
        result.loc[df.index >= break_close_time] = True
        return result

    # ------------------------------------------------------------------
    # Phase 4 — signal evaluation
    # ------------------------------------------------------------------
    def is_buy_signal(self, df_data: pd.DataFrame) -> dict:
        symbol = df_data["symbol"].iloc[0] if "symbol" in df_data.columns else "UNKNOWN"
        last = df_data.iloc[-1]
        last_time = df_data.index.max()

        current_str = last_time.strftime("%H:%M") if hasattr(last_time, "strftime") else ""
        in_window = self.session_start_time <= current_str <= self.entry_cutoff_time

        dir_long = bool(last.get("dir_long", False))
        retest = bool(last.get("retest_long", False))
        hammer = bool(last.get("hammer", False))
        bull_engulf = bool(last.get("bull_engulf", False))

        buy = in_window and dir_long and retest and (hammer or bull_engulf)

        return {
            "symbol": symbol,
            "buy_signal": buy,
            "valid_trading_window": in_window,
            "dir_long": dir_long,
            "retest_long": retest,
            "hammer": hammer,
            "bull_engulf": bull_engulf,
            "signal_time": (
                last_time.strftime("%Y-%m-%d %H:%M:%S")
                if hasattr(last_time, "strftime") else str(last_time)
            ),
            "signal_close": float(last["close"]),
        }

    def on_bar(self, symbol: str, df: pd.DataFrame, positions) -> Signal | None:
        """Build a candle-range bracket on a confirmed long signal.

        Overrides the percentage-based default because this strategy sizes its
        stop from the candle range and targets 3R.
        """
        if symbol in positions:
            return None

        trace = self.is_buy_signal(df)
        if not trace.get("buy_signal"):
            return None

        last = df.iloc[-1]
        close = round(float(last["close"]), 2)
        prev_high = float(last["prev_high"])
        rng = float(last["range"])

        stop = round(prev_high - rng * 0.2, 2)
        risk = close - stop
        if risk <= 0:
            return None
        target = round(close + risk * 3, 2)

        signal = Signal(
            symbol=symbol,
            entry_price=close,
            stop_price=stop,
            target_price=target,
            quantity=self.default_quantity,
            reason="break_and_bounce_long",
            signal_time=df.index.max(),
            entry_type="MKT",
        )
        self._signals_emitted += 1
        return signal
