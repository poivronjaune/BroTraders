# BroTraders Bot — Architecture Upgrade

> **Purpose:** This document proposes a new architecture for the BroTraders
> trading engine. The goal is to evolve from a one-shot command-line pipeline
> into a persistent, event-driven trading session that can support strategies
> with any temporal shape — not only "evaluate once at 9:33 and stop."

---

## Table of Contents

1. [Introduction](#introduction)
2. [What the Current Architecture Cannot Do](#what-the-current-architecture-cannot-do)
3. [Core Design Principle — Event-Driven Session Loop](#core-design-principle)
4. [Summary of Logic and Flow](#summary-of-logic-and-flow)
5. [Component Overview](#component-overview)
6. [Phase 1 — Session Startup](#phase-1--session-startup)
7. [Phase 2 — Scanner](#phase-2--scanner)
8. [Phase 3 — Data Initialisation](#phase-3--data-initialisation)
9. [Phase 4 — Live Trading Loop](#phase-4--live-trading-loop)
10. [Phase 5 — Order Management](#phase-5--order-management)
11. [Phase 6 — Risk Management](#phase-6--risk-management)
12. [Phase 7 — Session Shutdown](#phase-7--session-shutdown)
13. [The Extended Strategy Interface](#the-extended-strategy-interface)
14. [How Existing Strategies Fit In](#how-existing-strategies-fit-in)
15. [How a New Strategy Would Use the Loop](#how-a-new-strategy-would-use-the-loop)
16. [File and Module Organisation](#file-and-module-organisation)

---

## Introduction

The current BroTraders pipeline is a linear sequence of five CLI commands:

```
scan → getdata → indicators → signals → orders
```

This works well for strategies that make **a single decision at a fixed point in
time** — for example, *"evaluate the gap at 9:33 and place bracket orders"*.
Once the orders are placed, the session is over. The command-line process exits.

However, most serious intraday strategies are **temporal** — they observe the
market continuously, build context over time, and generate signals at
unpredictable moments throughout the session. Examples include:

| Strategy | Requires |
|---|---|
| Opening Range Breakout | Set the range over 9:30–9:45, watch for a breakout until 15:30 |
| VWAP Reclaim | Monitor price relative to rolling VWAP every bar |
| Trend Continuation | Re-enter on pullbacks to the 9-EMA throughout the day |
| News-driven momentum | React to scanner updates throughout the session |

A command-line tool that starts, does work, and exits **cannot implement any of
these**. The new architecture must keep the connection alive, receive live data,
and continuously evaluate the strategy until the session ends.

---

## What the Current Architecture Cannot Do

Before describing the new design, it is worth being precise about the
limitations:

- **No persistent connection.** Each CLI command opens a TWS connection,
  does its work, and disconnects. There is no way to react to something that
  happens at 10:47.
- **No live data feed.** `getdata` fetches a historical snapshot of the last
  2 days. It has no mechanism to receive new bars as they form.
- **No intra-session state.** Each command reads from and writes to CSV files.
  There is no shared in-memory state (e.g., "we are in a position on NVDA").
- **No feedback loop.** When a fill arrives, the session is already over. There
  is no way for the strategy to react to fills (e.g., move a stop to
  break-even after the first target is hit).
- **Fixed evaluation cadence.** Signals are evaluated once, at a single point
  in time. A strategy that signals on the 47th bar of the day is simply not
  expressible.

---

## Core Design Principle

> **The bot is a long-running async session. Data arrives as events. The
> strategy decides what to do on each event. The session ends when the strategy
> says it is done, or when the session window closes.**

This shifts the mental model from:

```
run script → get answer → exit
```

to:

```
open session → subscribe to data → react to events → close session
```

The `ib_async` library already supports this model natively. It has an internal
event loop and exposes subscription-based APIs (`reqHistoricalDataAsync` with
`keepUpToDate=True`, `barUpdateEvent`) that deliver new 1-minute bars as they
close. The new architecture simply wraps this capability in a clean session
structure.

---

## Summary of Logic and Flow

The full session proceeds through seven phases in sequence. Within Phase 4, the
bot runs a continuous event loop until the session closes.

```
┌─────────────────────────────────────────────────────────────┐
│  PHASE 1 — SESSION STARTUP                                  │
│  Connect to TWS. Load strategy. Initialise all components.  │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│  PHASE 2 — SCANNER                                          │
│  Ask strategy for scanner definition. Run IBKR scan.        │
│  Pass results to strategy for filtering. Build watch list.  │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│  PHASE 3 — DATA INITIALISATION                              │
│  Fetch 2-day historical bars for each symbol.               │
│  Build in-memory DataFrames per symbol.                     │
│  Run add_indicators() on each.                              │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│  PHASE 4 — LIVE TRADING LOOP  ◄────────────────────────┐   │
│  Subscribe to live 1-min bar updates for all symbols.  │   │
│  On each new bar:                                       │   │
│    1. Append bar to symbol's DataFrame                  │   │
│    2. Re-run add_indicators()                           │   │
│    3. Call strategy.on_bar(symbol, df, positions)       │   │
│    4. If signal → send to Order Manager                 │   │
│    5. If fill event → call strategy.on_fill()           │   │
│    6. Call Risk Manager checks                          │   │
│  Loop until strategy.is_session_done() or end time     │   │
└────────────────────────┬───────────────────────────────┘   │
                         │ (exit condition met)               │
┌────────────────────────▼────────────────────────────────────┐
│  PHASE 5 — ORDER MANAGEMENT  (runs throughout Phase 4)      │
│  Place bracket orders. Track fills. Manage positions.       │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│  PHASE 6 — RISK MANAGEMENT  (runs throughout Phase 4)       │
│  Enforce position cap, daily-loss limit, kill switch.       │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│  PHASE 7 — SESSION SHUTDOWN                                 │
│  Close open positions. Cancel unfilled orders.              │
│  Save trade log. Disconnect from TWS.                       │
└─────────────────────────────────────────────────────────────┘
```

---

## Component Overview

The bot is composed of five loosely-coupled components. Each has a single
responsibility. They communicate by passing data — not by calling each other
directly wherever possible.

| Component | Responsibility |
|---|---|
| **BotSession** | Top-level orchestrator. Owns the IB connection. Coordinates phases. |
| **DataManager** | Historical fetch + live bar subscription. Maintains per-symbol DataFrames. Fires `on_bar` events. |
| **StrategyRunner** | Calls the active strategy's methods. Translates strategy decisions into signals. |
| **OrderManager** | Places and tracks orders. Maintains a position registry. Handles fill callbacks. |
| **RiskManager** | Cross-cutting guard. Blocks new orders if limits are breached. |

The active **Strategy** is a pure-logic class (no IB connection, no I/O). It
receives data as arguments and returns decisions. This keeps it testable and
interchangeable.

---

## Phase 1 — Session Startup

### What it does

The session startup initialises everything before any market interaction occurs.
It ensures that: the TWS connection is live, the strategy is loaded and
validated, all components are wired together, and the session's trading window
is established.

### How it works

1. Load the strategy class dynamically from `config.STRATEGY_FILE` (using the
   existing `importlib` pattern).
2. Instantiate the strategy and read its session configuration:
   - `session_start_time` — when to run the scanner (e.g., `"09:30"`)
   - `session_end_time` — when to close all positions (e.g., `"15:45"`)
   - `max_positions` — how many concurrent open positions are allowed
3. Connect to TWS using the existing `connect_with_retry` helper (with back-off).
4. Instantiate `DataManager`, `StrategyRunner`, `OrderManager`, `RiskManager`,
   wiring them together.
5. If the current time is before `session_start_time`, sleep until then.
6. Proceed to Phase 2.

### Key design decisions

- **The IB connection is opened once and kept alive for the entire session.**
  This is the fundamental change from the current architecture.
- **Session times live on the Strategy**, not in `config.py`. This allows
  different strategies to define different trading windows without changing
  global settings.

---

## Phase 2 — Scanner

### What it does

Exactly the same as the current `scan` command — but now it is one step in a
larger session rather than a standalone command. The strategy defines the scanner
subscription; the bot runs it and builds the watch list.

### How it works

1. Call `strategy.scanner()` to get the `ScannerSubscription` definition.
2. Call `ib.reqScannerDataAsync(subscription)` — same as today.
3. Pass the raw scan results to `strategy.on_scan_results(df_scan)`.
   - This is a new optional method. The default implementation returns all
     symbols. A strategy can filter, rank, or cap the list.
4. Store the resulting symbol list as the **watch list** for the session.

### What changes from today

Today, the scan results are saved to `1_scan_results.csv` and the process exits.
In the new architecture, the results live in memory and are passed directly to
Phase 3. CSV saving becomes optional (for audit purposes), not the primary data
path.

---

## Phase 3 — Data Initialisation

### What it does

For each symbol on the watch list, fetch 2 days of 1-minute OHLCV bars and run
the strategy's indicators on the resulting DataFrame. This gives the live loop
a warm, fully-loaded DataFrame to work with from the first bar onward.

### How it works

1. For each symbol, call `ib.reqHistoricalDataAsync(...)` with `durationStr="2 D"`,
   `barSizeSetting="1 min"`, `useRTH=False` — exactly as `save_data_async` does today.
2. Store the result in the `DataManager`'s in-memory dictionary:
   `{symbol: pd.DataFrame}`.
3. For each symbol, call `strategy.add_indicators(df)` to pre-compute all
   indicator columns.
4. Subscribe to live bar updates for each symbol (`keepUpToDate=True` on the
   same `reqHistoricalDataAsync` call, or via `reqRealTimeBarsAsync`). The
   `DataManager` registers a `barUpdateEvent` handler that fires each time a
   new 1-minute bar is confirmed.

### Key design decisions

- **Historical fetch and live subscription happen in the same call** when using
  `keepUpToDate=True`. IBKR delivers historical bars first, then seamlessly
  continues with live bars. This means the `DataManager` does not need to
  switch modes — it always appends incoming bars to the same DataFrame.
- **`add_indicators` is called once here on the full historical window**, and
  then called incrementally on each new bar in Phase 4. To avoid recomputing
  everything on every bar, `add_indicators` should be designed to compute only
  from a rolling tail when the DataFrame is large.

---

## Phase 4 — Live Trading Loop

### What it does

This is the heart of the new architecture. The bot sits in an async event loop,
waiting for new bars to arrive. Each new bar triggers a full evaluation cycle
for the affected symbol. The loop runs until either the strategy signals it is
done or the session end time is reached.

### How it works

When the `DataManager` receives a new confirmed bar for a symbol, it fires a
`bar_ready` event with `(symbol, updated_df)`. The `StrategyRunner` is the
registered handler for this event. It executes the following sequence on every
bar for every symbol:

```
bar_ready(symbol, df)
    │
    ├── 1. Append new bar to df
    │
    ├── 2. Re-run strategy.add_indicators(df)
    │       (incremental — only last N rows need recomputing)
    │
    ├── 3. Call strategy.on_bar(symbol, df, current_positions)
    │       → returns: Signal | None
    │
    ├── 4. If Signal returned:
    │       → Pass signal to RiskManager.approve(signal)
    │           → If approved: pass to OrderManager.place(signal)
    │           → If rejected: log reason and skip
    │
    ├── 5. Check strategy.is_session_done()
    │       → If True: exit loop, proceed to Phase 7
    │
    └── 6. Check current_time >= session_end_time
            → If True: proceed to Phase 7
```

Fill events from IBKR arrive separately via `ib.execDetailsEvent`. The
`OrderManager` handles these and can call `strategy.on_fill(symbol, fill)` to
notify the strategy. This allows strategies to react to fills — for example,
tightening a stop after the first partial target is hit.

### Why this works for all strategy types

The key is that **`strategy.on_bar()` is called for every bar regardless of the
strategy**. Each strategy decides internally what to do with it:

- The **gap rise strategy** checks the time window. If it is 09:30–09:45, it
  evaluates. Outside that window it returns `None`. Once all positions are
  placed, `is_session_done()` returns `True`.
- An **opening range strategy** builds the range silently during 09:30–09:45
  (returning `None`). After 09:45 it watches for breakouts on every bar and
  returns a signal when the breakout occurs.
- A **VWAP reclaim strategy** computes VWAP on every bar and signals whenever
  price crosses above VWAP with volume confirmation — potentially multiple
  times per day.

None of this requires changing the bot. Only the strategy's `on_bar()` logic
changes. The loop is universal.

---

## Phase 5 — Order Management

### What it does

The `OrderManager` is the single component that interacts with the IB order
API during the live loop. It receives approved signals from the `StrategyRunner`,
places bracket orders, tracks the state of every open position, and handles fill
callbacks.

### How it works

**Placing an order:**

1. Receive an approved signal containing: `symbol`, `entry_price`,
   `stop_price`, `target_price`, `quantity`.
2. Qualify the contract with `ib.qualifyContractsAsync`.
3. Place the bracket (parent limit + stop-loss + take-profit) — same logic as
   `place_order_async` today, but now using actual computed prices (not guesses
   from `signal_close`).
4. Record the trade in the **position registry**: a dictionary mapping
   `symbol → PositionState`.
5. Subscribe to `ib.execDetailsEvent` for fill notifications.

**Tracking fills:**

When the parent order fills, update `PositionState.entry_price` with the actual
fill price. Optionally recompute the stop and target based on actual fill (see
fix #15 in `fix.md`). When either the stop or target fills, mark the position
closed and call `strategy.on_fill(symbol, fill_summary)`.

**Position registry:**

The registry is the in-memory equivalent of `3_placed_orders.csv`. It stores:
- Order IDs for parent, stop-loss, take-profit
- Current status of each leg
- Entry fill price, exit fill price
- P&L as it becomes known

At the end of the session (Phase 7), the registry is serialised to the trade
log.

### What changes from today

Today, `track_orders.py` is a separate process that reconnects to IBKR and
queries execution history. In the new architecture, **fills are received in
real time via event callbacks** inside the same session. `track_orders.py` can
remain as a reconciliation tool for runs that crashed unexpectedly, but it is
no longer the primary tracking mechanism.

---

## Phase 6 — Risk Management

### What it does

The `RiskManager` is a cross-cutting guard that runs alongside the live loop. It
does not generate signals or place orders — it only approves or blocks them.
Every signal from `StrategyRunner` must pass through `RiskManager.approve()`
before reaching `OrderManager`.

### Checks performed

| Check | Description |
|---|---|
| **Max concurrent positions** | Block new entries if `len(open_positions) >= max_positions` |
| **Daily-loss limit** | Block new entries if today's realised P&L is below `-MAX_DAILY_LOSS_USD` |
| **Already in position** | Block a second entry on a symbol already in the position registry |
| **Session time** | Block new entries after `entry_cutoff_time` (e.g., 15:30 — no new positions in the last 15 min) |
| **Kill switch** | A manual flag file (e.g., `DATA/KILL`) that halts all trading when present |

### Kill switch implementation

The kill switch is a simple file-presence check: if `DATA/KILL` exists, the
`RiskManager` blocks all new orders and signals the bot to proceed to Phase 7.
The user can create this file at any time from another terminal window to halt
the bot without killing the process (which would leave the TWS connection in an
undefined state).

---

## Phase 7 — Session Shutdown

### What it does

Cleanly closes the trading session: cancels unfilled orders, closes any open
positions (if the strategy instructs), saves the trade log, and disconnects from
TWS.

### How it works

1. **Cancel unfilled orders:** For every entry in the position registry where
   the parent order has not yet filled, cancel the parent (and its children
   if TWS has not already auto-cancelled them).
2. **Close open positions (optional):** If `strategy.close_on_session_end` is
   `True`, send market-sell orders for all open positions before disconnecting.
   Some strategies (with GTC stops) may prefer to leave positions open overnight
   — this is a strategy-level decision.
3. **Save trade log:** Serialise the full position registry to `4_trades.csv`
   (or the SQLite database if issue #29 from `fix.md` is implemented).
4. **Save session summary:** Write a brief summary (number of signals, filled
   orders, total P&L) to a log file.
5. **Disconnect:** Call `ib.disconnect()`. The IB event loop is stopped cleanly.

---

## The Extended Strategy Interface

To support continuous operation, the `Strategy` class gains several new methods
and properties alongside the existing ones. All new methods have sensible
defaults so that the existing `gap_rise` strategy requires minimal changes.

### Existing interface (unchanged)

| Method / Property | Description |
|---|---|
| `scanner()` | Returns the IBKR `ScannerSubscription` |
| `add_indicators(df)` | Adds computed columns to a DataFrame |
| `is_buy_signal(df)` | Evaluates all rules and returns a trace dict |

### New interface additions

| Method / Property | Default | Description |
|---|---|---|
| `session_start_time` | `"09:30"` | When the scanner should run |
| `session_end_time` | `"16:00"` | When to trigger Phase 7 |
| `entry_cutoff_time` | `"15:30"` | No new entries after this time |
| `max_positions` | `3` | Max concurrent open positions |
| `close_on_session_end` | `False` | Whether to market-close open positions at session end |
| `on_scan_results(df)` | Returns all symbols | Strategy can filter/rank the watch list |
| **`on_bar(symbol, df, positions)`** | Calls `is_buy_signal` | Called on every new bar. Returns a `Signal` or `None`. This is the primary extension point. |
| `on_fill(symbol, fill)` | No-op | Called when any leg of a bracket fills. Strategy can react (e.g., adjust stops). |
| `is_session_done()` | `False` | Returns `True` when the strategy has nothing more to do (e.g., all positions placed and no more re-entries allowed). Triggers early shutdown. |

### The Signal object

`on_bar` returns either `None` (no trade) or a `Signal` dataclass:

```
Signal:
    symbol          : str
    entry_price     : float      # limit price for entry order
    stop_price      : float      # stop-loss price
    target_price    : float      # take-profit price
    quantity        : int        # position size
    reason          : str        # human-readable description of why signal fired
    signal_time     : datetime   # timestamp of the triggering bar
```

This replaces the ad-hoc `conditions_trace` dict that `is_buy_signal` returns
today with a typed, structured object that the `OrderManager` can act on
directly.

---

## How Existing Strategies Fit In

The `gap_rise` strategy adapts to the new interface with minimal changes:

1. **`on_bar(symbol, df, positions)`** — delegates to the existing
   `is_buy_signal(df)` logic. If the result has `buy_signal == True` and the
   symbol is not already in `positions`, it returns a `Signal`.

2. **`is_session_done()`** — returns `True` once `max_positions` signals have
   been placed. Since the gap strategy only trades in the 09:30–09:45 window,
   after that window closes and positions are placed, there is nothing more to
   do.

3. **All other new methods** use the defaults — no changes required.

The existing `is_buy_signal`, `add_indicators`, and `scanner` methods are
untouched. The gap rise strategy is a valid bot strategy with approximately
15 lines of new code.

---

## How a New Strategy Would Use the Loop

Consider an **Opening Range Breakout** strategy as a concrete example of a
strategy that requires the continuous loop.

### Desired behaviour

1. From 09:30 to 09:45, observe price for each symbol. Record the high and low
   of that range.
2. After 09:45, watch every bar. If price closes **above the opening high**
   on above-average volume, generate a buy signal.
3. Stop = opening range low. Target = entry + (opening high − opening low).
4. Do not enter after 14:00.
5. Close all positions at 15:45.

### How this maps to the interface

| Interface method | Opening Range Breakout implementation |
|---|---|
| `session_start_time` | `"09:30"` |
| `session_end_time` | `"15:45"` |
| `entry_cutoff_time` | `"14:00"` |
| `add_indicators(df)` | Compute `opening_range_high`, `opening_range_low`, rolling volume average |
| `on_bar(symbol, df, positions)` | Before 09:45 → return `None` (building range). After 09:45 → check breakout condition, return `Signal` if triggered. |
| `on_fill(symbol, fill)` | Optional: log fill, tighten stop after partial fill |
| `is_session_done()` | Return `True` when `max_positions` reached or `entry_cutoff_time` has passed and all positions are closed |
| `close_on_session_end` | `True` — close any open positions at 15:45 |

The bot loop does not change at all. Only the strategy file is different. This
confirms that the architecture is strategy-agnostic.

---

## File and Module Organisation

The new architecture adds four new modules and promotes `services.py` into
a thinner helper layer.

```
brotools/
├── __init__.py
├── __main__.py             # keeps existing CLI commands + adds `run_bot`
├── config.py               # keeps existing settings + session defaults
├── log_config.py           # logging setup (from fix #4)
├── strategy_protocol.py    # Strategy Protocol/ABC (from fix #1)
│
├── bot_session.py          # NEW — BotSession orchestrator (Phases 1 + 7)
├── data_manager.py         # NEW — DataManager (Phases 3 + 4 data layer)
├── strategy_runner.py      # NEW — StrategyRunner (Phase 4 evaluation)
├── order_manager.py        # NEW — OrderManager (Phase 5)
├── risk_manager.py         # NEW — RiskManager (Phase 6)
│
├── services.py             # kept — scanner logic (Phase 2), reused by BotSession
├── trading_indicators.py   # kept — pure pandas helpers
├── trading_rules.py        # kept — pure rule functions
├── track_orders.py         # kept — post-session reconciliation fallback
├── datacleaning.py         # kept
│
└── strategies/
    ├── gap_rise.py          # updated — adds on_bar(), is_session_done()
    └── open_range.py        # example new strategy
```

### New `run_bot` command

A single new entry point replaces the five-step pipeline for continuous
strategies:

```
run_bot = "brotools.bot_session:run"
```

The existing five CLI commands (`scan`, `getdata`, `indicators`, `signals`,
`orders`) remain available for manual inspection, backtesting, and one-off use.
They are not removed. `run_bot` is the production entry point; the individual
commands are the development and debugging tools.

---

*Document generated as part of the BroTraders architecture upgrade review.*
*See `todo.md` for the full issue list and `fix.md` for detailed fix guides.*
