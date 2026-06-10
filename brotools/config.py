IBKR_HOST = '127.0.0.1'
IBKR_PORT = 7497      # Trader Work Station (TWS)
#IBKR_PORT = 4002      # IB_GATEWAY
IBKR_CLIENT_ID = 0
STRATEGY_FILE = "gap_rise.py"
#STRATEGY_FILE = "stub_strategy.py"

# ---------------------------------------------------------------------------
# Connection resilience (used by connect_with_retry)
# ---------------------------------------------------------------------------
CONNECT_RETRIES = 3
CONNECT_DELAY   = 5.0   # seconds, doubled on each retry (exponential back-off)

# ---------------------------------------------------------------------------
# Live bot session
# ---------------------------------------------------------------------------
# Manual kill switch: create this file from another terminal to halt the bot
# and trigger a clean shutdown (Phase 7) without killing the process.
KILL_SWITCH_FILE = "DATA/KILL"