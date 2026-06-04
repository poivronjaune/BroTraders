# BroTraders — TODO: Weaknesses & Risks

This file captures all weaknesses and risks identified during the architecture review.
Items are grouped by category and ordered roughly by priority within each group.

---

## 🐍 Python Practices

- [✅] ~~**Fix hard-coded strategy import in `services.py`** (line 23):
  `from brotools.strategies.gap_rise import Strategy` defeats the dynamic strategy
  loader in `__main__.py`. Switching `STRATEGY_FILE` in `config.py` won't fully
  work. Use the same `importlib` pattern as `__main__.py`.~~
- [✅] ~~**Remove duplicate `Strategy` instantiation** in `add_indicators()`
  (`__main__.py` lines 40 and 42). The first instantiation is dead code.~~
- [✅] ~~**Replace bare `except Exception`** in `get_report_async`, `save_data_async`,
  and `place_orders_async`. They swallow everything so partial failures look
  like success. Catch specific exceptions and re-raise or log with context.~~
- [✅] ~~**Add a logging framework** — replace `print(...)` calls with the `logging`
  module, with file handlers for audit trails (essential for live trading).~~
- [ ] **Add type hints** on most functions (only a few have them today).
- [ ] **Add tests** — there are no unit or integration tests. The pure functions
  in `trading_rules.py` and `trading_indicators.py` are easy wins.
- [ ] **Add a dependency lockfile** (`uv.lock`, `poetry.lock`, or
  `requirements.txt`) for reproducible installs.
- [ ] **Centralize hard-coded paths** — `DATA/...` strings are scattered across
  modules. Move to a single config constant.
- [ ] **Parameterize the `START_BOUND` literal** in `datacleaning.py`
  (`"2026-05-28 04:00:00"` is a hard-coded date string).
- [ ] **Fix README install command**: `py install -e .` should be
  `py -m pip install -e .`.
- [ ] **Replace manual `sys.argv` parsing** in `datacleaning.py` with
  `argparse`, `click`, or `typer`.
- [✅] ~~**Remove unused `pytz` dependency** from `pyproject.toml` (declared but never imported).~~

---

## 📈 Day-Trading Robustness

- [ ] **Add risk-based position sizing** — `DEFAULT_QUANTITY = 1` ignores
  account equity and stop distance. Size based on risk-per-trade % and
  distance to stop.
- [ ] **Recompute brackets from actual fill price**, not `signal_close`
  (last 1-min bar). Slippage on a gapping small cap can easily be 1–2 %,
  which makes a 2 % stop wafer-thin and a 5 % target unrealistic.
- [ ] **Add volatility-adjusted stops** (ATR, VWAP, prior-day range), instead
  of fixed `STOP_LOSS_PCT` / `TAKE_PROFIT_PCT`.
- [ ] **Replace market order on entry with marketable-limit** (or
  limit-on-open) — market orders in $10–$200 fast movers cause heavy slippage.
- [ ] **Add a max-concurrent-positions cap** — currently the scanner could
  legitimately return 50 buy signals and the script would fire 50 brackets.
- [ ] **Add a daily-loss limit / kill switch** that halts new entries after
  a threshold is hit.
- [ ] **Add a correlation / sector filter** — without it the system can go
  long several names in the same catalyst (e.g., biotech).
- [ ] **Account for commissions, spread, and borrow** in the signal logic,
  not only post-trade in `4_trades.csv`.
- [ ] **Make `check_candles_up` tolerant to first-bar timing** — currently it
  requires the first RTH bar to be exactly `09:30`; IBKR sometimes returns
  it slightly later, causing silent rule failures.
- [ ] **Add a backtest harness** — rules are already pure functions, but there
  is no walk-forward, no metrics, no historical replay. Trading a hypothesis
  on live capital without this is risky.
- [ ] **Change `IBKR_CLIENT_ID` away from `0`** — clientId 0 collides with
  TWS's reserved/manual-order client and can confuse order state when
  multiple tools run.
- [ ] **Add reconnection / heartbeat logic** — if TWS drops mid-session the
  script dies. Server-side GTC stops mitigate the position risk, but the
  tracking workflow won't recover.

---

## 🧑‍💻 Ease of Use

- [ ] **Replace the manual five-command workflow with a single orchestrator**
  (e.g., `run-morning`) — running `signals` before `indicators` completes
  silently uses stale data.
- [ ] **Eliminate the wall-clock dependency** ("run at 9:33") — provide an
  async orchestrator that waits for 09:30 ET and chains the whole pipeline.
- [ ] **Add an explicit `--paper / --live` flag** — today only the TWS port
  (`7497` vs `4002`) distinguishes paper from live trading. That is a
  dangerous foot-gun.
- [ ] **Move off CSV-as-database** for state — concurrent runs corrupt files,
  and there is no schema validation. SQLite or Parquet would be safer.
- [ ] **Raise on errors instead of printing them** — the pipeline currently
  prints `❌ ...` and continues, making it easy to miss a failed step.
