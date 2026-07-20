"""
brotoolsv2.config

Global bot configuration: IBKR connection settings plus v2 portfolio/risk
settings (position sizing, exposure caps, kill-switch).
See TODO/bot_upgrade_v2.md for the requirements behind these values.
"""

# ---------------------------------------------------------------------------
# IBKR connection settings (carried over from brotools/config.py)
# ---------------------------------------------------------------------------
IBKR_HOST = '127.0.0.1'
IBKR_PORT = 7497       # Trader Work Station (TWS)
# IBKR_PORT = 4002      # IB Gateway
IBKR_CLIENT_ID = 0

# ---------------------------------------------------------------------------
# Position sizing
# ---------------------------------------------------------------------------
RISK_PCT_PER_TRADE = 0.02   # 2% of account equity risked per trade

# ---------------------------------------------------------------------------
# Portfolio exposure caps (independent circuit breakers)
# ---------------------------------------------------------------------------
MAX_CONCURRENT_POSITIONS = 8       # Max open positions, across all active strategies
MAX_EQUITY_DEPLOYED_PCT = 0.20     # Max % of equity deployed at once (sum of entry_price * shares)

# ---------------------------------------------------------------------------
# Daily loss kill-switch
# ---------------------------------------------------------------------------
DAILY_LOSS_KILL_SWITCH_PCT = 0.10  # Blocks new positions when day's P&L loss hits 10% of equity
