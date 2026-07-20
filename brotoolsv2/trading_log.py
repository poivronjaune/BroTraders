"""
brotoolsv2.trading_log

SQLite-backed trading log (DATA/trades.db). Lifecycle-based: one row per
trade in the `trades` table, updated in place as it progresses
(PLACED -> FILLED -> CLOSED, or PLACED -> CANCELLED), plus one row per
individual IBKR order (entry/stop/target) in the `orders` table.
"""
