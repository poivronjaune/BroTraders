# BroTraders Bot — Upgrade Requirements v2

> **Status:** Requirements discussion — record of decisions made before implementation.
> **Supersedes / extends:** `TODO/bot_upgrade.md` (original event-driven session proposal).
> **Purpose:** Capture the finalized requirements for turning BroTraders from a
> manual five-command CLI pipeline into a persistent, multi-strategy, risk-managed
> trading bot that can be launched once in the morning (e.g. 7:00–7:30 AM) and run
> unattended through the session.

---

## Table of Contents

1. [Why This Upgrade](#why-this-upgrade)
2. [Execution Model](#execution-model)
3. [Multi-Strategy Support](#multi-strategy-support)
4. [Global Watchlist & Symbol Locking](#global-watchlist--symbol-locking)
5. [Risk Management & Position Sizing](#risk-management--position-sizing)
6. [Portfolio Exposure Caps](#portfolio-exposure-caps)
7. [Daily Loss Kill-Switch](#daily-loss-kill-switch)
8. [Global Bot Configuration](#global-bot-configuration)
9. [Trading Log (SQLite)](#trading-log-sqlite)
10. [Open Items — Not Yet Defined](#open-items--not-yet-defined)

---

## Why This Upgrade

The current pipeline (`scan → getdata → indicators → signals → orders`) is a
sequence of independent CLI commands. Each one connects to TWS, does one job,
and disconnects. This works for a strategy that evaluates once at a fixed time
(e.g. "check the gap at 9:33") but cannot:

- React to price action throughout the day
- Monitor a position after the order is placed
- Run more than one strategy at once
- Scale position size to account equity or risk
- Track order lifecycle (placed → filled → closed) in one place

The goal of this upgrade is a **single long-running session** that starts in
the morning, stays connected, and reacts to events (new scan results, new
price bars, order fills) until shutdown.

---

## Execution Model

- The bot is launched once, around **7:00–7:30 AM**, and stays alive through
  the trading session (this replaces manually running five separate commands).
- The bot maintains **one persistent TWS connection** for the whole session.
- Data model: **one shared live-bar subscription mechanism for all watchlist
  symbols**, all on **1-minute bars**. This is a first-iteration simplification —
  no per-symbol or per-strategy bar-size configuration for now. Day-trading
  strategies are the intended use case, so 1-min resolution is sufficient.
- General flow (adapted from `TODO/bot_upgrade.md`, extended for multi-strategy):
  1. **Startup** — connect to TWS, load all strategies, read each strategy's
     `active` flag once (see below).
  2. **Recurring scan** — each active strategy's scanner is re-run on an
     interval (not just once), continuously adding new candidates to the
     watchlist as they qualify.
  3. **Warm-up** — when a symbol first appears on the watchlist, pull
     historical 1-min bars (same as today's `getdata` step) to give the
     strategy context (previous close, opening range, etc.).
  4. **Live monitoring** — once warmed up, the symbol's data feed switches to
     live/near-real-time 1-min bars. Every new completed bar triggers an
     indicator recompute and a signal check for that symbol, for every
     strategy that has it on its candidate list.
  5. **Order placement on signal** — when a strategy's signal check passes
     (and the symbol is not already in an open position — see [Global
     Watchlist](#global-watchlist--symbol-locking)), the bot builds and
     submits the order immediately.
  6. **Continued monitoring post-trade** — after a trade is placed, the bot
     keeps watching that symbol's live bars and order fill events. This is a
     capability the current pipeline does not have at all (the process exits
     right after placing orders today).
  7. **Shutdown** — at a defined time or manual stop, the bot stops accepting
     new signals and disconnects cleanly. **No forced flattening of open
     positions on shutdown** (see [Daily Loss Kill-Switch](#daily-loss-kill-switch)
     for the related no-flatten decision on the kill-switch).

---

## Multi-Strategy Support

- The bot loads **every `Strategy` class found in `brotools/strategies/`**,
  not just the single strategy referenced by `STRATEGY_FILE` today.
- Each strategy defines an **`active` flag** (e.g. `self.active = True`).
  Only strategies with `active = True` are scanned, monitored, and traded.
- The `active` flag is **read once at session startup**. It is **not**
  toggled while the bot is running — changing it requires editing the
  strategy and restarting the session. No runtime flag-flipping.
- If only one strategy is active, behavior is equivalent to today's
  single-strategy pipeline. As more strategies are added and flagged active,
  the bot evaluates all of them concurrently, increasing the number of
  trading opportunities checked per scan cycle / per bar.

---

## Global Watchlist & Symbol Locking

- There is **one shared/global watchlist**, not a separate watchlist per
  strategy.
- Each watchlist entry tracks:
  - The symbol
  - The list of strategies that have flagged it as a candidate (a symbol can
    be flagged by more than one active strategy at the same time)
  - The **owning strategy** — `None` until a position is actually opened on
    that symbol
  - Current position status for that symbol
- **Locking rule:** when a strategy's signal check passes and it is ready to
  place an order, it may only proceed if the bot currently has **no open
  position** on that symbol — regardless of which strategy would be placing
  it.
- Once a position is opened on a symbol, that symbol is **locked to the
  strategy that opened it**. All other strategies must skip evaluating or
  acting on that symbol until the position is fully closed (flat again).
- This requires a shared `symbol → open position / owning strategy` registry
  that every strategy's order-placement step checks before acting.

---

## Risk Management & Position Sizing

- **Position sizing method:** percent of account equity risked per trade
  (not fixed dollar risk, not fixed share count).
  ```
  shares = (equity × risk_pct) / (entry_price − stop_price)
  ```
- **Capital pool:** shared across all active strategies. There is no
  per-strategy capital partition — any active strategy can use available
  capital until a portfolio-level limit is hit.
- **Important distinction (clarified during discussion):** *risk per trade*
  and *capital deployed per trade* are not the same number and do not map to
  each other without knowing the stop distance:
  - Risk per trade = `(entry_price − stop_price) × shares` — the dollar
    amount that could be lost if the stop is hit.
  - Capital deployed per trade = `entry_price × shares` — the dollar amount
    actually committed to the position.
  - A tight stop means more shares are needed to hit the same dollar-risk
    target, which means **more capital deployed** for the same risk
    percentage. E.g., risking 1% of equity with a stop only 2% below entry
    deploys roughly 50% as much capital as the risk percentage might suggest
    at first glance — the two numbers are decoupled.

---

## Portfolio Exposure Caps

Three **independent** circuit breakers apply simultaneously. They are not
derived from one another (a symbol/strategy with a tight stop can hit the
deployed-capital cap well before hitting the position-count cap, and vice
versa). Whichever limit is hit first blocks new entries.

| Cap | Value | Applies to |
|---|---|---|
| Max concurrent open positions | **8** | Total, across all active strategies combined |
| Max % of equity deployed at once | **20%** | Sum of `entry_price × shares` across all open positions, as a percent of total account equity |
| Daily loss kill-switch | **10%** (default, configurable — see below) | See dedicated section below |

These are independent because position sizing is risk-based (percent of
equity), not deployed-capital-based — actual capital deployed per trade
varies with stop distance, so a fixed relationship between "8 positions" and
"20% deployed" cannot be assumed or engineered in.

---

## Daily Loss Kill-Switch

- Triggers when the day's realized + unrealized loss reaches **10% of total
  account equity** (default value — see [Global Bot
  Configuration](#global-bot-configuration) for how this is set/changed).
- Measured against **total account equity** (start-of-day value), not
  against deployed capital or risk budget.
- **Effect when triggered:** blocks the bot from opening **new** positions
  only.
- **Explicitly does NOT:**
  - Force-close or flatten any existing open positions.
  - Cancel existing bracket orders (stop-loss / take-profit) already
    working on open positions.
- Existing positions continue running under their own stop-loss / take-profit
  orders exactly as placed, unaffected by the kill-switch.
- A separate, more aggressive "flatten everything on kill-switch" behavior
  was discussed and explicitly **rejected** for this iteration — if wanted
  later, it would need to be a distinct, separately-controlled flag.
- Default threshold ships at **10%** (the original discussion considered
  35%, judged too aggressive relative to typical daily-loss circuit breakers
  for day trading, and revised down to 10%).

---

## Global Bot Configuration

All portfolio/risk parameters below must live in **one global bot
configuration**, not hardcoded inside strategy files and not scattered
across modules — this extends the existing `brotools/config.py` pattern
(which already centralizes IBKR connection settings) to cover portfolio and
risk settings as well, so they can be changed easily without touching
strategy or bot logic code:

- Position sizing method and risk % per trade
- Max concurrent open positions (default: 8)
- Max % of equity deployed at once (default: 20%)
- Daily loss kill-switch threshold (default: 10% of total equity)
- (Existing) IBKR host/port/client ID, strategy loading behavior

---

## Trading Log (SQLite)

- A **dedicated SQLite database** (e.g. `DATA/trades.db`), kept **separate**
  from the existing programming/debug log (`brotools/log_config.py` /
  `LOGS/brotraders.log`). The trading log is a business record, not a
  debug/audit trail.
- **Lifecycle-based, not event-based:** one row per trade is created **at
  order placement time** — whether or not the order ever fills — and that
  **same row is updated in place** as the trade progresses. This is *not* a
  running log with a separate "buy" entry and a separate "sell" entry;
  there is one row per trade whose status and fields evolve over time.
  - Status progression: `PLACED → FILLED → CLOSED`, or `PLACED → CANCELLED`
    if the order never fills.
  - Written/updated at order placement, at fill, at close (stop or target
    hit), and flushed again at shutdown to capture anything left in an
    intermediate state (e.g. a position still open at end of day).
- **Order hierarchy / bracket tracking:** trades are not flat single orders —
  a bracket order has a parent (entry) and children (stop-loss, take-profit).
  The schema needs **two related tables**, not one flat table:
  - `trades` — one row per round-trip trade. Tracks strategy used, symbol,
    overall lifecycle status, entry/exit summary, and P&L once known.
  - `orders` — one row per individual IBKR order (parent entry, stop-loss,
    take-profit, and any other child orders). Each row links back to its
    trade via `trade_id`, is tagged with a `role` (e.g. `entry`, `stop`,
    `target`), and carries its own IBKR order ID and status.
  - This allows a bracket's full structure to be traced (parent + both
    children), and supports later modifications to a child order (e.g.
    moving a stop to breakeven) as an update to that child's row rather than
    a new row.
- Fields to capture per trade (non-exhaustive, to be finalized at schema
  design time): strategy name, symbol, entry time/price, exit time/price,
  quantity, exit reason (stop/target/manual), gross P&L, commissions, net
  P&L, order IDs, status.

---

## Open Items — Not Yet Defined

These were identified during the requirements discussion but intentionally
deferred to later design/implementation sessions:

- Exact `Strategy` interface — hook method signatures (`on_scan_results`,
  `on_bar`, `on_fill`, `is_session_done`, etc.) and what parameters each
  receives.
- Module/file structure — what new files are added to `brotools/`, and what
  `services.py` / `__main__.py` keep vs. lose.
- Full SQLite schema (column-level detail, indexes, constraints) for the
  `trades` and `orders` tables.
- Scan interval, warm-up window size, and other per-strategy timing
  parameters referenced in the execution model but not yet numerically
  defined.
- Whether/how commissions and slippage estimates feed into the risk
  calculations before order placement (raised as a possible future
  improvement in `TODO/fix.md` issue #21, not yet folded into this upgrade).

---

*Document generated from the BroTraders bot-upgrade requirements discussion.*
*See `TODO/bot_upgrade.md` for the original event-driven session architecture
proposal this document extends, and `TODO/todo.md` / `TODO/fix.md` for the
broader outstanding issue list.*
