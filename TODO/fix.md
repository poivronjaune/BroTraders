# BroTraders — Fix Guide

This document walks through fixes for issues identified in `todo.md`, one at a
time. Each issue uses the structure:

- `##` Issue title
- `###` Problem summary
- `###` Fix summary
- `###` Detailed explanation
- `###` Code snippets

---

## 1. Hard-coded strategy import in `services.py`
Status: Fixed  

### Problem summary

In `brotools/services.py` (line 23), the `Strategy` class is imported
directly from a specific strategy module:

```python
from brotools.strategies.gap_rise import Strategy
```

This contradicts the design in `brotools/__main__.py`, which dynamically loads
the strategy module based on the `STRATEGY_FILE` setting in
`brotools/config.py`:

```python
module_name = STRATEGY_FILE.replace('.py', '')
strategy_module = importlib.import_module(f"brotools.strategies.{module_name}")
Strategy = strategy_module.Strategy
```

As a result, if a user creates a new strategy (e.g. `gap_fall.py`) and updates
`STRATEGY_FILE = "gap_fall.py"` in `config.py`, the CLI commands defined in
`__main__.py` will load the new strategy, but anything in `services.py` that
references `Strategy` will silently keep using `gap_rise.Strategy`. The
"pluggable strategy" promise is broken.

In addition, the import is currently only used as a **type hint** on
`get_report_async(strategy: Strategy)` — it is not used to instantiate the
class — so the runtime coupling is unnecessary. The actual `Strategy` instance
is always passed in from `__main__.py`.

### Fix summary

Remove the hard-coded import from `services.py` and rely on the strategy
instance being passed in by the caller. Replace the `Strategy` type hint with
a forward reference (string) or a `TYPE_CHECKING` guarded import so the type
hint stays accurate without creating a runtime dependency on a specific
strategy module.

### Detailed explanation

1. **File to change:** `brotools/services.py`.

2. **Remove** the runtime import:

   ```python
   from brotools.strategies.gap_rise import Strategy
   ```

3. **Add** a `TYPE_CHECKING` block at the top of the file so the type hint
   on `get_report_async(strategy: "Strategy")` still resolves for static
   analysis (mypy, Pyright, IDE) without importing anything at runtime:

   ```python
   from typing import TYPE_CHECKING
   if TYPE_CHECKING:
       from brotools.strategies.gap_rise import Strategy  # any concrete impl
   ```

   Note: this `TYPE_CHECKING` import is only for editor tooling. It does
   **not** force `gap_rise` to be the strategy at runtime — callers pass in
   whichever strategy was dynamically loaded.

4. **Update the function signature** of `get_report_async` to use the
   forward-reference form `"Strategy"` so Python does not try to resolve the
   name at import time:

   ```python
   async def get_report_async(strategy: "Strategy") -> pd.DataFrame | None:
   ```

5. **(Optional, recommended) Define a Protocol** to formalize the contract
   that `services.py` actually depends on. Today it only calls
   `strategy.scanner()`. A Protocol makes the duck-typing explicit and lets
   any strategy module implement it without inheritance. Add a new file
   `brotools/strategy_protocol.py`:

   ```python
   from typing import Protocol
   from ib_async import ScannerSubscription

   class StrategyProtocol(Protocol):
       def scanner(self) -> ScannerSubscription: ...
   ```

   Then in `services.py` use the Protocol as the type hint instead of the
   concrete class — no `TYPE_CHECKING` block required:

   ```python
   from brotools.strategy_protocol import StrategyProtocol
   ...
   async def get_report_async(strategy: StrategyProtocol) -> pd.DataFrame | None:
   ```

6. **No changes are needed** in `__main__.py`, `config.py`, or any strategy
   file. The dynamic loader in `__main__.py` already produces a `Strategy`
   instance and passes it into `get_report_async`, so step 1 is sufficient
   for correctness; steps 3–5 only improve type accuracy.

7. **Verify** by:
   - Adding a second strategy file under `brotools/strategies/` (e.g. a stub
     `gap_fall.py` with its own `Strategy` class and `scanner()` method).
   - Setting `STRATEGY_FILE = "gap_fall.py"` in `config.py`.
   - Running `scan` and confirming the printed strategy name comes from the
     new module (`__enter__` prints `self.name`).

### Code snippets

**Before — `brotools/services.py` (top of file):**

```python
import asyncio
from datetime import datetime
from pathlib import Path

import pandas as pd
from ib_async import IB, Stock, util, MarketOrder, LimitOrder, StopOrder

from brotools.config import IBKR_HOST, IBKR_PORT, IBKR_CLIENT_ID
from brotools.strategies.gap_rise import Strategy
```

**After — minimal fix using `TYPE_CHECKING`:**

```python
import asyncio
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd
from ib_async import IB, Stock, util, MarketOrder, LimitOrder, StopOrder

from brotools.config import IBKR_HOST, IBKR_PORT, IBKR_CLIENT_ID

if TYPE_CHECKING:
    # Imported only for type-checking; runtime strategy is injected by the caller.
    from brotools.strategies.gap_rise import Strategy
```

**After — recommended fix using a Protocol** (`brotools/strategy_protocol.py`):

```python
from typing import Protocol
from ib_async import ScannerSubscription


class StrategyProtocol(Protocol):
    """Minimal contract that services.py relies on."""

    def scanner(self) -> ScannerSubscription: ...
```

**After — updated `services.py` top with Protocol:**

```python
import asyncio
from datetime import datetime
from pathlib import Path

import pandas as pd
from ib_async import IB, Stock, util, MarketOrder, LimitOrder, StopOrder

from brotools.config import IBKR_HOST, IBKR_PORT, IBKR_CLIENT_ID
from brotools.strategy_protocol import StrategyProtocol
```

**Updated function signature in `services.py`:**

```python
async def get_report_async(strategy: StrategyProtocol) -> pd.DataFrame | None:
    """
    Run an IBKR scanner using the provided strategy and return results.
    ...
    """
    ib = IB()
    df = None
    try:
        scanner = strategy.scanner()
        await ib.connectAsync(IBKR_HOST, IBKR_PORT, clientId=IBKR_CLIENT_ID)
        ...
```

**No-op verification snippet** — drop a stub strategy at
`brotools/strategies/gap_fall.py`, point `config.py` at it, and run `scan`:

```python
# brotools/strategies/gap_fall.py
from ib_async import ScannerSubscription


class Strategy:
    def __init__(self):
        self.name = "Gap Fall Strategy (stub)"

    def __enter__(self):
        print(f"Opening connection to {self.name}.")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        print(f"Closing connection to {self.name} safely.")

    def scanner(self) -> ScannerSubscription:
        sub = ScannerSubscription()
        sub.numberOfRows = 50
        sub.instrument = "STK"
        sub.locationCode = "STK.US.MAJOR"
        sub.scanCode = "TOP_PERC_LOSE"
        return sub
```

```python
# brotools/config.py
STRATEGY_FILE = "gap_fall.py"
```

Run `scan` — the console should print `Opening connection to Gap Fall Strategy (stub).`,
confirming the dynamic loader in `__main__.py` is now the single source of
truth for which strategy is active.

---

### Extra features  
Added a new column in the scan results to keep track of the strategy name used for scanner results.  

<hr>
<hr>
<hr>


## 2. Duplicate `Strategy` instantiation in `add_indicators()`  
Status: Fixed    
  
### Problem summary

In `brotools/__main__.py`, the `add_indicators()` function instantiates the
`Strategy` class twice in a row:

```python
def add_indicators() -> None:
    strategy = Strategy()                      # line 40 — dead code
    tickers = pd.read_csv("DATA/1_scan_results.csv")["symbol"].tolist()
    with Strategy() as strategy:               # line 42 — actual instance used
        for ticker in tickers:
            ...
```

The first instance (line 40) is bound to the local name `strategy` and then
immediately overwritten by the `with Strategy() as strategy:` block on line
42. The first instance is never used: its `__enter__` is never called, so the
"Opening connection to ..." message is skipped for it, but the constructor
still runs. This is dead code that:

- Clutters the function and confuses readers ("why two instances?").
- Wastes work if `__init__` ever becomes expensive or has side effects
  (e.g. opening a connection, reading a config file).
- Risks future bugs if someone adds setup logic to `__init__` and assumes
  both instances behave identically.

### Fix summary

Delete the first `strategy = Strategy()` line. The `with Strategy() as strategy:`
context manager is the only instantiation needed.

### Detailed explanation

1. **File to change:** `brotools/__main__.py`.

2. **Function to change:** `add_indicators()`.

3. **Action:** remove the line `strategy = Strategy()` that appears just
   before the `tickers = pd.read_csv(...)` line. No other change is needed —
   the `with Strategy() as strategy:` block on the following line already
   produces a properly initialized instance bound to the same name and
   ensures `__exit__` runs for cleanup.

4. **No callers are affected.** The only `strategy` reference inside the
   function is `strategy.add_indicators(df_data)` inside the `with` block,
   which uses the context-managed instance.

5. **Verify** by running `indicators` after the change. The console should
   print:

   ```
   Opening connection to Gap Rise Strategy.
   ... (one log line per ticker)
   Closing connection to Gap Rise Strategy safely.
   ```

   If you previously saw any double "Opening connection ..." or any
   leftover side effect from the dead instance, it should now be gone.

### Code snippets

**Before — `brotools/__main__.py` `add_indicators()`:**

```python
def add_indicators() -> None:
    strategy = Strategy()
    tickers = pd.read_csv("DATA/1_scan_results.csv")["symbol"].tolist()
    with Strategy() as strategy:
        for ticker in tickers:
            df_data = pd.read_csv(
                f"DATA/{ticker}.csv",
                index_col="date",
                parse_dates=["date"]
            )
            df_data = strategy.add_indicators(df_data)
            df_data.to_csv(f'DATA/{ticker}.csv')
            print(df_data.head())
```

**After — `brotools/__main__.py` `add_indicators()`:**

```python
def add_indicators() -> None:
    tickers = pd.read_csv("DATA/1_scan_results.csv")["symbol"].tolist()
    with Strategy() as strategy:
        for ticker in tickers:
            df_data = pd.read_csv(
                f"DATA/{ticker}.csv",
                index_col="date",
                parse_dates=["date"]
            )
            df_data = strategy.add_indicators(df_data)
            df_data.to_csv(f'DATA/{ticker}.csv')
            print(df_data.head())
```

**Diff view:**

```diff
 def add_indicators() -> None:
-    strategy = Strategy()
     tickers = pd.read_csv("DATA/1_scan_results.csv")["symbol"].tolist()
     with Strategy() as strategy:
         for ticker in tickers:
             df_data = pd.read_csv(
                 f"DATA/{ticker}.csv",
                 index_col="date",
                 parse_dates=["date"]
             )
             df_data = strategy.add_indicators(df_data)
             df_data.to_csv(f'DATA/{ticker}.csv')
             print(df_data.head())
```

---

<hr>
<hr>
<hr>

## 3. Replace bare `except Exception` in async service functions  
Status: Fixed  
  
### Problem summary

In `brotools/services.py`, all three async orchestrators (`get_report_async`,
`save_data_async`, `place_orders_async`) use a catch-all `except Exception as e:`
that prints an error and then either returns `None` or silently continues. This
means partial failures — a bad contract, a pacing violation, a lost connection
— look identical to success from the caller's perspective. The pipeline keeps
moving and the user only notices the problem downstream (e.g., an empty signals
file).

### Fix summary

Replace the bare `except Exception` blocks with narrower exception types where
possible, and re-raise (or propagate a clear sentinel) so the calling CLI
command can abort the pipeline with an informative error instead of silently
succeeding with bad data.

### Detailed explanation

1. **File to change:** `brotools/services.py`.

2. **Functions to change:** `get_report_async`, `save_data_async`,
   `place_orders_async`.

3. For `get_report_async`: the most likely failures are `ConnectionRefusedError`
   (TWS not running) and `asyncio.TimeoutError` (scan timed out). Catch those
   specifically and re-raise so `get_scan()` in `__main__.py` sees the error.

4. For `save_data_async`: failures can be per-ticker (pacing violation, unknown
   symbol) or connection-level. Catch per-ticker errors inside the loop but
   propagate connection errors.

5. For `place_orders_async`: order failures are per-symbol and should be
   collected, reported at the end, and cause a non-zero exit if any failed.

6. In `__main__.py` CLI entry points, wrap the calls with a top-level
   `try/except` that prints a clear message and calls `sys.exit(1)` on failure,
   ensuring the shell sees a non-zero exit code.

### Code snippets

**Before — `get_report_async` catch-all:**

```python
    except Exception as e:
        print(f"❌ Error during scan: {e}")
```

**After — specific exceptions, re-raise:**

```python
    except ConnectionRefusedError:
        print("❌ Could not connect to TWS — is Trader Workstation running on "
              f"{IBKR_HOST}:{IBKR_PORT}?")
        raise
    except Exception as e:
        print(f"❌ Unexpected error during scan: {type(e).__name__}: {e}")
        raise
```

**Before — `save_data_async` swallows everything:**

```python
    except Exception as e:
        print(f"❌ An error occurred: {e}")
```

**After — distinguish connection errors from per-ticker errors:**

```python
    except ConnectionRefusedError:
        print("❌ Could not connect to TWS.")
        raise
    except Exception as e:
        print(f"❌ Unexpected connection error: {type(e).__name__}: {e}")
        raise
```

Inside the ticker loop, wrap per-ticker fetches individually:

```python
        for ticker in tickers:
            try:
                contract = Stock(ticker, "SMART", "USD") if isinstance(ticker, str) \
                           else Stock(conId=ticker)
                await ib.qualifyContractsAsync(contract)
                bars = await ib.reqHistoricalDataAsync(...)
                if bars:
                    ...
                else:
                    print(f"⚠️  No data returned for {contract.symbol}")
            except Exception as e:
                print(f"❌ Failed to fetch data for {ticker}: {type(e).__name__}: {e}")
                # continue to next ticker instead of aborting the whole batch
            await asyncio.sleep(0.1)
```

**`__main__.py` — CLI entry point with exit code:**

```python
import sys

def get_scan():
    with Strategy() as strategy:
        try:
            scan_result = asyncio.run(get_report_async(strategy))
        except Exception:
            sys.exit(1)
    if scan_result is not None:
        scan_result.to_csv("DATA/1_scan_results.csv", index=False)
        print(f"Scan report saved {len(scan_result)} prospects.")
    else:
        print("❌ Scan returned no results.")
        sys.exit(1)
```

---

## 4. Add a logging framework  
Status: Fixed  
  
### Problem summary

All feedback to the user is delivered via `print()` calls scattered across
`services.py`, `track_orders.py`, `datacleaning.py`, and `__main__.py`. In a
live trading system this means:

- No persistent audit trail of what happened during a session.
- No log levels — informational noise is indistinguishable from warnings.
- No easy way to redirect output or filter severity.
- When the terminal is closed, everything is lost.

### Fix summary

Introduce Python's built-in `logging` module with a shared configuration that
writes to both the console (INFO level) and a rotating file (`logs/brotools.log`,
DEBUG level). Replace all `print()` calls in non-interactive code with
appropriate `logger.*()` calls.

### Detailed explanation

1. **New file:** `brotools/log_config.py` — central logging setup, called once
   at startup.

2. **Each module** gets its own logger via `logger = logging.getLogger(__name__)`.

3. **Emoji prefixes** (`✅`, `❌`, `⚠️`) can be kept in the message text for
   console readability; the log file will capture them too.

4. **`__main__.py`** calls `configure_logging()` at the top of each entry
   point before doing any work.

5. Print statements in `datacleaning.py`, `track_orders.py`, and
   `services.py` are replaced with `logger.info / logger.warning / logger.error`.

### Code snippets

**New file — `brotools/log_config.py`:**

```python
import logging
import logging.handlers
from pathlib import Path

LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "brotools.log"

def configure_logging(level: str = "INFO") -> None:
    LOG_DIR.mkdir(exist_ok=True)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)  # capture everything; handlers filter

    fmt = logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler — INFO and above
    console = logging.StreamHandler()
    console.setLevel(getattr(logging, level.upper(), logging.INFO))
    console.setFormatter(fmt)

    # Rotating file handler — DEBUG and above, 5 × 1 MB
    file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=1_000_000, backupCount=5, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)

    root.addHandler(console)
    root.addHandler(file_handler)
```

**Each module — module-level logger:**

```python
import logging
logger = logging.getLogger(__name__)
```

**Replacing print calls — example in `services.py`:**

```python
# Before
print(f"💾 Saved {len(bars)} rows to {filepath}")
print(f"⚠️  No data returned for {contract.symbol}")
print(f"❌ An error occurred: {e}")

# After
logger.info("💾 Saved %d rows to %s", len(bars), filepath)
logger.warning("⚠️  No data returned for %s", contract.symbol)
logger.error("❌ An error occurred: %s: %s", type(e).__name__, e)
```

**`__main__.py` — call configure at entry points:**

```python
from brotools.log_config import configure_logging

def get_scan():
    configure_logging()
    with Strategy() as strategy:
        ...
```

---

## 5. Add type hints on functions

### Problem summary

Most functions in `brotools/` lack parameter and return type annotations.
Without them, IDEs and static analysers (mypy, Pyright) cannot catch type
errors before runtime — especially important when dealing with DataFrames,
IB order objects, and mixed `int | str` contract identifiers.

### Fix summary

Add `-> return_type` annotations and typed parameters to all public functions.
Use `pd.DataFrame`, `list[str]`, `Path`, and `tuple` precisely. Use
`from __future__ import annotations` at the top of each file for forward
references.

### Detailed explanation

1. Add `from __future__ import annotations` to the top of each module so
   string forward references are resolved lazily.
2. Annotate function signatures in `services.py`, `trading_rules.py`,
   `trading_indicators.py`, `track_orders.py`, and `datacleaning.py`.
3. Run `mypy brotools/` (after `pip install mypy`) to find remaining issues.

### Code snippets

**`brotools/trading_rules.py` — before:**

```python
def check_trading_window(df_data, start_time="09:30", end_time="10:00"):
def check_gap_size(df_data, gap_threshold=10.0):
def check_candles_up(df_data, consecutive=3, start_rth="09:30", end_rth="16:00"):
```

**After:**

```python
from __future__ import annotations
import pandas as pd

def check_trading_window(
    df_data: pd.DataFrame,
    start_time: str = "09:30",
    end_time: str = "10:00",
) -> tuple[str, bool]:

def check_gap_size(
    df_data: pd.DataFrame,
    gap_threshold: float = 10.0,
) -> tuple[str, bool]:

def check_candles_up(
    df_data: pd.DataFrame,
    consecutive: int = 3,
    start_rth: str = "09:30",
    end_rth: str = "16:00",
) -> tuple[str, bool]:
```

**`brotools/services.py` — selected functions:**

```python
def load_buy_signals(filepath: Path = BUY_SIGNALS_FILE) -> pd.DataFrame:
def create_bracket_order(qte: int = DEFAULT_QUANTITY, estimated_buy_price: float = 100.0) -> tuple:
def build_buy_orders(df_signals: pd.DataFrame) -> list[dict]:
def save_placed_orders(placed_orders: list[dict], filepath: Path) -> None:
async def save_data_async(tickers: list[str | int], timeframe: str | None = None, back_days: int | None = None) -> None:
```

---

## 6. Add unit tests

### Problem summary

There are zero tests. The pure functions in `trading_rules.py` and
`trading_indicators.py` are untested, meaning a refactor or edge-case bug
(e.g., a ticker with no RTH data, a gap of exactly 10 %) could silently
produce wrong signals and place bad orders.

### Fix summary

Add a `tests/` folder with `pytest` unit tests for the pure functions.
Start with `trading_rules.py` and `trading_indicators.py` since they have no
external dependencies and are easy to test with small DataFrames.

### Detailed explanation

1. Add `pytest` to `pyproject.toml` as a dev dependency.
2. Create `tests/__init__.py` (empty) and test files named
   `tests/test_trading_rules.py`, `tests/test_trading_indicators.py`.
3. Build minimal DataFrames with `pd.date_range` to simulate 1-min OHLCV data.
4. Run with `pytest tests/`.

### Code snippets

**`pyproject.toml` — add dev dependencies:**

```toml
[project.optional-dependencies]
dev = ["pytest", "pytest-asyncio", "mypy"]
```

**`tests/test_trading_rules.py`:**

```python
import pandas as pd
import pytest
from brotools.trading_rules import check_trading_window, check_gap_size, check_candles_up


def make_df(times: list[str], opens: list[float], closes: list[float]) -> pd.DataFrame:
    idx = pd.to_datetime([f"2024-01-15 {t}" for t in times])
    return pd.DataFrame({"open": opens, "close": closes,
                         "high": closes, "low": opens, "volume": [1000] * len(times)},
                        index=idx)


def test_check_trading_window_inside():
    df = make_df(["09:35"], [100.0], [101.0])
    name, result = check_trading_window(df, "09:30", "09:45")
    assert name == "valid_trading_window"
    assert result is True


def test_check_trading_window_outside():
    df = make_df(["10:00"], [100.0], [101.0])
    _, result = check_trading_window(df, "09:30", "09:45")
    assert result is False


def test_check_gap_size_above_threshold():
    df = make_df(["09:30"], [100.0], [101.0])
    df["gap_percent"] = 12.0
    _, result = check_gap_size(df, gap_threshold=10.0)
    assert result is True


def test_check_gap_size_below_threshold():
    df = make_df(["09:30"], [100.0], [101.0])
    df["gap_percent"] = 5.0
    _, result = check_gap_size(df, gap_threshold=10.0)
    assert result is False


def test_check_candles_up_three_green():
    times  = ["09:30", "09:31", "09:32", "09:33"]
    opens  = [100.0, 101.0, 102.0, 103.0]
    closes = [100.5, 101.5, 102.5, 103.5]  # all green
    df = make_df(times, opens, closes)
    _, result = check_candles_up(df, consecutive=3)
    assert result is True


def test_check_candles_up_one_red():
    times  = ["09:30", "09:31", "09:32", "09:33"]
    opens  = [100.0, 101.5, 102.0, 103.0]
    closes = [100.5, 101.0, 102.5, 103.5]  # 09:31 is red
    df = make_df(times, opens, closes)
    _, result = check_candles_up(df, consecutive=3)
    assert result is False
```

---

## 7. Add a dependency lockfile

### Problem summary

`pyproject.toml` pins only `requires-python = ">=3.12"` with no version bounds
on `pandas`, `ib_async`, or `pytz`. Anyone installing the project on a
different date may get different package versions, potentially breaking
behaviour (e.g., pandas API changes, `ib_async` protocol changes).

### Fix summary

Generate a lockfile using `pip-compile` (from `pip-tools`) or migrate to `uv`
which produces a `uv.lock` file automatically. Commit the lockfile so installs
are fully reproducible.

### Detailed explanation

1. **Option A — `pip-tools`** (minimal change, works with existing setup):
   - `pip install pip-tools`
   - `pip-compile pyproject.toml -o requirements.lock`
   - Add `requirements.lock` to the repo.
   - Install with `pip install -r requirements.lock`.

2. **Option B — `uv`** (modern, fast):
   - `pip install uv`
   - `uv lock` (generates `uv.lock` from `pyproject.toml`)
   - `uv sync` to install from the lock.
   - Add `uv.lock` to the repo.

3. Update `README.md` install section to use the lockfile.

### Code snippets

**Option A — generate and install:**

```bash
pip install pip-tools
pip-compile pyproject.toml -o requirements.lock
pip install -r requirements.lock
```

**Option B — using uv:**

```bash
pip install uv
uv lock          # generates uv.lock
uv sync          # installs exact locked versions
```

**Updated README install block:**

```markdown
## Installation

```bash
py -3.12 -m venv .venv
.\.venv\Scripts\activate
py -m pip install -U pip pip-tools
pip-compile pyproject.toml -o requirements.lock
pip install -r requirements.lock
pip install -e .
```
```

---

## 8. Centralize hard-coded `DATA/` paths

### Problem summary

The string `"DATA/"` (and variants like `"DATA/1_scan_results.csv"`) appears
hardcoded in at least five files: `__main__.py`, `services.py`,
`track_orders.py`, `datacleaning.py`, and `strategies/gap_rise.py`
(implicitly via callers). If the user wants to change the data directory they
must update every file manually and risk missing one.

### Fix summary

Define all data paths as `Path` constants in `brotools/config.py` and import
them wherever needed. Replace every `"DATA/..."` string literal with the
corresponding constant.

### Detailed explanation

1. **File to change:** `brotools/config.py` — add `Path` constants.
2. **Files to update:** `__main__.py`, `services.py`, `track_orders.py`,
   `datacleaning.py` — replace literals with imported constants.

### Code snippets

**`brotools/config.py` — add path constants:**

```python
from pathlib import Path

IBKR_HOST      = '127.0.0.1'
IBKR_PORT      = 7497
IBKR_CLIENT_ID = 0
STRATEGY_FILE  = "gap_rise.py"

# Data directory — change this one line to relocate all data files
DATA_DIR             = Path("DATA")
SCAN_RESULTS_FILE    = DATA_DIR / "1_scan_results.csv"
BUY_SIGNALS_FILE     = DATA_DIR / "2_buy_signals.csv"
PLACED_ORDERS_FILE   = DATA_DIR / "3_placed_orders.csv"
TRADES_FILE          = DATA_DIR / "4_trades.csv"
```

**`brotools/__main__.py` — import and use:**

```python
from brotools.config import IBKR_HOST, IBKR_PORT, IBKR_CLIENT_ID, STRATEGY_FILE, \
                            SCAN_RESULTS_FILE, BUY_SIGNALS_FILE, DATA_DIR

def get_scan():
    with Strategy() as strategy:
        scan_result = asyncio.run(get_report_async(strategy))
        if scan_result is not None:
            scan_result.to_csv(SCAN_RESULTS_FILE, index=False)

def get_data() -> None:
    tickers = pd.read_csv(SCAN_RESULTS_FILE)["symbol"].tolist()
    asyncio.run(save_data_async(tickers))
```

**`brotools/services.py` — replace literals:**

```python
# Before
BUY_SIGNALS_FILE   = Path("DATA/2_buy_signals.csv")
PLACED_ORDERS_FILE = Path("DATA/3_placed_orders.csv")
HISTORICAL_DATA_DIR = Path("DATA")

# After
from brotools.config import BUY_SIGNALS_FILE, PLACED_ORDERS_FILE, DATA_DIR as HISTORICAL_DATA_DIR
```

---

## 9. Parameterize `START_BOUND` in `datacleaning.py`

### Problem summary

`datacleaning.py` contains a module-level hard-coded constant:

```python
START_BOUND = "2026-05-28 04:00:00"
```

This is a specific calendar date that becomes wrong every trading day. A user
running `clean` weeks later will silently keep the wrong start boundary unless
they remember to edit the source file.

### Fix summary

Add a `--start_bound` CLI flag (mirroring the existing `--end_bound` flag) so
both boundaries are supplied at runtime. If `--start_bound` is omitted, default
to midnight of the current day so the behaviour is sensible without requiring
a flag every time.

### Detailed explanation

1. **File to change:** `brotools/datacleaning.py`.
2. Remove the `START_BOUND` module constant.
3. Add `-start_bound` flag parsing alongside `-end_bound` using the same
   `sys.argv` approach (or migrate to `argparse` — see issue 11).
4. Default `start_bound` to `"today 00:00:00"` when omitted.

### Code snippets

**Before:**

```python
START_BOUND = "2026-05-28 04:00:00"

def clean_historical_data():
    ...
    start_ts = pd.to_datetime(START_BOUND).tz_localize(None)
```

**After:**

```python
def clean_historical_data():
    args = sys.argv[1:]
    end_bound_input = None
    start_bound_input = None

    if "-end_bound" in args:
        idx = args.index("-end_bound")
        end_bound_input = " ".join(args[idx + 1:]).strip()

    if "-start_bound" in args:
        idx = args.index("-start_bound")
        # end_bound may also be in argv; take only the date portion
        end_idx = args.index("-end_bound") if "-end_bound" in args else len(args)
        start_bound_input = " ".join(args[idx + 1: end_idx]).strip()

    if not end_bound_input:
        current_dt_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print("❌ Error: Missing required parameter '-end_bound'.")
        print(f'\n💡 Usage: clean -end_bound "{current_dt_str}" [-start_bound "YYYY-MM-DD HH:MM:SS"]')
        return

    # Default start to today midnight if not provided
    if not start_bound_input:
        start_bound_input = datetime.now().strftime("%Y-%m-%d 00:00:00")

    start_ts = pd.to_datetime(start_bound_input).tz_localize(None)
    end_ts   = pd.to_datetime(end_bound_input).tz_localize(None)
```

---

## 10. Fix README install command

### Problem summary

The README installation block contains:

```
py install -e .
```

This is not a valid command — `py install` is not a Python launcher command.
The correct invocation is `py -m pip install -e .`.

### Fix summary

Update the README code block with the correct `py -m pip install -e .` command.

### Detailed explanation

1. **File to change:** `README.md`.
2. Replace `py install -e .` with `py -m pip install -e .`.

### Code snippets

**Before — `README.md`:**

```markdown
```
py -3.12 -m venv .venv
.\.venv\Scripts\activate
py -m pip install -U pip
py install -e .
```
```

**After — `README.md`:**

```markdown
```
py -3.12 -m venv .venv
.\.venv\Scripts\activate
py -m pip install -U pip
py -m pip install -e .
```
```

---

## 11. Replace manual `sys.argv` parsing with `argparse`

### Problem summary

`datacleaning.py` manually walks `sys.argv` to find `-end_bound`:

```python
args = sys.argv[1:]
if "-end_bound" in args:
    flag_idx = args.index("-end_bound")
    end_bound_input = " ".join(args[flag_idx + 1:]).strip()
```

This is fragile: argument order matters, flags can be confused with values,
there is no `--help`, and adding more flags (like `--start_bound` from issue 9)
requires more manual slicing. Python's `argparse` (stdlib) solves all of this
for free.

### Fix summary

Replace the `sys.argv` block in `clean_historical_data()` with an `argparse`
parser. The function signature stays the same (`clean` console script entry
point), but argument parsing becomes robust and auto-documents itself via
`--help`.

### Detailed explanation

1. **File to change:** `brotools/datacleaning.py`.
2. Remove all `sys.argv` import and parsing.
3. Add an `argparse.ArgumentParser` with `--start_bound` and `--end_bound`
   arguments.

### Code snippets

**Before:**

```python
import sys
...
args = sys.argv[1:]
end_bound_input = None
if "-end_bound" in args:
    try:
        flag_idx = args.index("-end_bound")
        end_bound_input = " ".join(args[flag_idx + 1:]).strip()
    except IndexError:
        pass
if not end_bound_input:
    ...
    return
```

**After:**

```python
import argparse
...
def clean_historical_data():
    parser = argparse.ArgumentParser(
        prog="clean",
        description="Trim historical ticker CSVs to a specific time window.",
    )
    parser.add_argument(
        "--end_bound", required=True,
        metavar="YYYY-MM-DD HH:MM:SS",
        help="Keep rows up to and including this datetime.",
    )
    parser.add_argument(
        "--start_bound",
        metavar="YYYY-MM-DD HH:MM:SS",
        default=datetime.now().strftime("%Y-%m-%d 00:00:00"),
        help="Keep rows from this datetime onwards (default: today midnight).",
    )
    args = parser.parse_args()

    try:
        start_ts = pd.to_datetime(args.start_bound).tz_localize(None)
        end_ts   = pd.to_datetime(args.end_bound).tz_localize(None)
    except Exception as e:
        print(f"❌ Datetime parsing error: {e}")
        raise SystemExit(1)
    ...
```

**Usage after the fix:**

```bash
clean --end_bound "2026-06-03 16:00:00"
clean --end_bound "2026-06-03 16:00:00" --start_bound "2026-06-02 04:00:00"
clean --help
```

---

## 12. Remove unused `pytz` dependency  
Status: Fixed  
  
### Problem summary

`pyproject.toml` lists `pytz` as a runtime dependency, but `pytz` is never
imported anywhere in the `brotools/` package. Since Python 3.9+, `zoneinfo`
(stdlib) covers timezone needs, and `pandas` bundles its own timezone handling.
The unused dependency adds install weight and a maintenance burden.

### Fix summary

Remove `"pytz"` from the `dependencies` list in `pyproject.toml`. No code
changes are needed.

### Detailed explanation

1. **File to change:** `pyproject.toml`.
2. Remove the `"pytz"` entry from the `dependencies` list.
3. Run `pip install -e .` again to sync the environment.
4. Verify with `grep -r "pytz" brotools/` — should return no results.

### Code snippets

**Before — `pyproject.toml`:**

```toml
dependencies = [
    "pandas",
    "ib_async",
    "pytz"
]
```

**After:**

```toml
dependencies = [
    "pandas",
    "ib_async",
]
```

---

## 13. Implement or remove the `live_trades()` stub

### Problem summary

`brotools/__init__.py` contains:

```python
def live_trades():
    print('Not implemented yet....')
```

This function is wired to the `run_live` console script in `pyproject.toml`.
A user who runs `run_live` gets a misleading message with no guidance on what
to do instead. It also implies a broken feature exists.

### Fix summary

Either implement the function or remove both the stub and its `pyproject.toml`
entry. If implementation is deferred, replace it with a `NotImplementedError`
and a helpful message pointing the user to the five-step manual pipeline.

### Detailed explanation

1. **File to change:** `brotools/__init__.py`.
2. **File to change:** `pyproject.toml` (remove `run_live` entry if removing
   the feature).
3. Decide: implement or remove.

### Code snippets

**Option A — raise clearly with guidance (deferred implementation):**

```python
# brotools/__init__.py
def live_trades():
    raise NotImplementedError(
        "Live auto-trading loop is not yet implemented.\n"
        "Use the manual pipeline instead:\n"
        "  scan → getdata → indicators → signals → orders"
    )
```

**Option B — remove stub and console script:**

```python
# brotools/__init__.py — remove live_trades() entirely
```

```toml
# pyproject.toml — remove this line
run_live = "brotools.__init__:live_trades"
```

---

## 14. Add risk-based position sizing

### Problem summary

`services.py` uses `DEFAULT_QUANTITY = 1` for every order, regardless of
account size, stock price, or stop distance. At $200/share with a 2 % stop
that is a $4 risk — trivially small. At $10/share with a wider stop it might
be fine. The system has no concept of how much capital to risk per trade.

### Fix summary

Add a `RISK_PER_TRADE_USD` constant and compute quantity from
`risk / (entry_price - stop_price)`. Retrieve account equity from IBKR once
per session and optionally cap risk at a % of equity.

### Detailed explanation

1. **File to change:** `brotools/services.py` — `create_bracket_order` and
   `build_buy_orders`.
2. Add `RISK_PER_TRADE_USD` to `config.py` (e.g. $50).
3. Compute `stop_price = round(estimated_buy_price * STOP_LOSS_PCT, 2)`.
4. Compute `quantity = max(1, int(RISK_PER_TRADE_USD / (estimated_buy_price - stop_price)))`.
5. Pass `quantity` into `create_bracket_order` instead of `DEFAULT_QUANTITY`.

### Code snippets

**`brotools/config.py`:**

```python
RISK_PER_TRADE_USD = 50.0   # max dollars to risk on a single trade
```

**`brotools/services.py` — updated `build_buy_orders`:**

```python
from brotools.config import RISK_PER_TRADE_USD, STOP_LOSS_PCT

def build_buy_orders(df_signals: pd.DataFrame) -> list[dict]:
    orders = []
    for _, signal in df_signals.iterrows():
        contract        = Stock(signal["symbol"], "SMART", "USD")
        estimated_price = round(signal["signal_close"], 2)
        stop_price      = round(estimated_price * STOP_LOSS_PCT, 2)
        risk_per_share  = estimated_price - stop_price
        quantity        = max(1, int(RISK_PER_TRADE_USD / risk_per_share)) \
                          if risk_per_share > 0 else 1
        parent, stop_loss, take_profit = create_bracket_order(quantity, estimated_price)
        orders.append({
            "symbol":      signal["symbol"],
            "contract":    contract,
            "parent":      parent,
            "stop_loss":   stop_loss,
            "take_profit": take_profit,
        })
    return orders
```

---

## 15. Recompute brackets from actual fill price

### Problem summary

Bracket prices (`stop_loss`, `take_profit`) are calculated in
`build_buy_orders` using `signal_close` — the close of the last 1-minute bar
before the signal was generated. By the time the market order fills (even
seconds later in a fast-moving gapper), the actual fill price can be 1–2 %
higher due to slippage. This compresses the effective stop from 2 % to nearly
zero and makes the 5 % target harder to reach.

### Fix summary

Move bracket price calculation to after the parent order fills.
In `place_order_async`, wait for the parent `Trade` to reach `Filled` status,
read the actual fill price from `trade.orderStatus.avgFillPrice`, then compute
and submit the stop-loss and take-profit at that price.

### Detailed explanation

1. **File to change:** `brotools/services.py` — `place_order_async`.
2. Place the parent market order with `transmit=True` (standalone).
3. Wait for it to fill: poll `trade.orderStatus.status == "Filled"`.
4. Read `fill_price = parent_trade.orderStatus.avgFillPrice`.
5. Compute stop and target from `fill_price`, then place child orders.

### Code snippets

**Updated `place_order_async` in `services.py`:**

```python
async def place_order_async(ib: IB, item: dict) -> dict:
    contract = item["contract"]
    quantity = item["quantity"]

    await ib.qualifyContractsAsync(contract)

    # Place standalone market buy — transmit immediately
    parent = MarketOrder("BUY", quantity, tif="GTC", transmit=True)
    parent_trade = ib.placeOrder(contract, parent)

    # Wait for fill (timeout after 30 seconds)
    for _ in range(300):
        await asyncio.sleep(0.1)
        if parent_trade.orderStatus.status == "Filled":
            break
    else:
        raise TimeoutError(f"{item['symbol']}: parent order not filled within 30s")

    fill_price = parent_trade.orderStatus.avgFillPrice
    stop_price   = round(fill_price * STOP_LOSS_PCT, 2)
    target_price = round(fill_price * TAKE_PROFIT_PCT, 2)

    stop_loss   = StopOrder("SELL", quantity, stop_price,  tif="GTC",
                            parentId=parent.orderId, transmit=False)
    take_profit = LimitOrder("SELL", quantity, target_price, tif="GTC",
                             parentId=parent.orderId, transmit=True)

    sl_trade = ib.placeOrder(contract, stop_loss)
    tp_trade = ib.placeOrder(contract, take_profit)
    await asyncio.sleep(0)

    print(f"✅ {item['symbol']} filled @ {fill_price:.2f} | SL {stop_price} | TP {target_price}")
    return {"symbol": item["symbol"], "parent_trade": parent_trade,
            "sl_trade": sl_trade, "tp_trade": tp_trade}
```

---

## 16. Add volatility-adjusted stops

### Problem summary

`STOP_LOSS_PCT = 0.98` and `TAKE_PROFIT_PCT = 1.05` are fixed percentages
applied equally to a $10 stock and a $200 stock. A $10 stock with a 2 %
stop ($0.20) can be stopped out by normal bid/ask spread noise, while a
$200 stock with the same stop ($4.00) may be too tight relative to its ATR.

### Fix summary

Compute a stop distance based on the stock's Average True Range (ATR), then
set the stop at `entry - k * ATR` and target at `entry + R * k * ATR`
(where R is the reward-to-risk ratio). Add ATR calculation to
`trading_indicators.py` and expose `ATR_MULTIPLIER` and `REWARD_RISK_RATIO`
in `config.py`.

### Detailed explanation

1. **New function** `compute_atr(df, period=14)` in `trading_indicators.py`.
2. **`Strategy.add_indicators`** in `gap_rise.py` calls it to add an
   `atr` column.
3. **`services.py`** reads `signal["atr"]` from the buy signals DataFrame
   and uses it to set bracket prices.
4. **`config.py`** exposes `ATR_MULTIPLIER = 1.5` and `REWARD_RISK_RATIO = 2.0`.

### Code snippets

**`brotools/trading_indicators.py` — new function:**

```python
def compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range over `period` bars."""
    high  = df["high"]
    low   = df["low"]
    close = df["close"].shift(1)
    tr = pd.concat([high - low,
                    (high - close).abs(),
                    (low  - close).abs()], axis=1).max(axis=1)
    return tr.rolling(period).mean()
```

**`brotools/strategies/gap_rise.py` — `add_indicators`:**

```python
from brotools.trading_indicators import prev_day_closing_bar, current_day_opening_bar, compute_atr

def add_indicators(self, df_data: pd.DataFrame) -> pd.DataFrame:
    ...
    df_data["atr"] = compute_atr(df_data)
    return df_data
```

**`brotools/config.py`:**

```python
ATR_MULTIPLIER    = 1.5   # stop = entry - ATR_MULTIPLIER * atr
REWARD_RISK_RATIO = 2.0   # target = entry + REWARD_RISK_RATIO * stop_distance
```

**`brotools/services.py` — `build_buy_orders` with ATR stops:**

```python
from brotools.config import ATR_MULTIPLIER, REWARD_RISK_RATIO

def build_buy_orders(df_signals: pd.DataFrame) -> list[dict]:
    orders = []
    for _, signal in df_signals.iterrows():
        contract        = Stock(signal["symbol"], "SMART", "USD")
        estimated_price = round(signal["signal_close"], 2)
        atr             = signal.get("atr", None)

        if atr and not pd.isna(atr):
            stop_distance = round(ATR_MULTIPLIER * atr, 2)
        else:
            # Fallback to fixed percentage if ATR is unavailable
            stop_distance = round(estimated_price * (1 - STOP_LOSS_PCT), 2)

        stop_price   = round(estimated_price - stop_distance, 2)
        target_price = round(estimated_price + REWARD_RISK_RATIO * stop_distance, 2)
        risk_per_share = estimated_price - stop_price
        quantity = max(1, int(RISK_PER_TRADE_USD / risk_per_share)) if risk_per_share > 0 else 1

        parent    = MarketOrder("BUY",  quantity, tif="GTC", transmit=False)
        stop_loss = StopOrder( "SELL", quantity, stop_price,   tif="GTC", transmit=False)
        take_profit = LimitOrder("SELL", quantity, target_price, tif="GTC", transmit=True)
        orders.append({"symbol": signal["symbol"], "contract": contract,
                       "quantity": quantity, "parent": parent,
                       "stop_loss": stop_loss, "take_profit": take_profit})
    return orders
```

---

## 17. Replace market order on entry with marketable-limit order

### Problem summary

`create_bracket_order` uses `MarketOrder("BUY", ...)`. In fast-moving
small-cap gap-up stocks ($10–$200), a market order can fill several percent
above the last observed price, eating the entire expected profit.

### Fix summary

Replace the parent `MarketOrder` with a `LimitOrder` priced slightly above the
current ask (a "marketable limit"), giving slippage protection while still
getting filled quickly. Add a `LIMIT_OFFSET_PCT` config value (e.g. 0.5 %)
that controls how much above `signal_close` the limit is set.

### Detailed explanation

1. **File to change:** `brotools/config.py` — add `LIMIT_OFFSET_PCT = 0.005`.
2. **File to change:** `brotools/services.py` — `create_bracket_order` (or
   `build_buy_orders`) — replace `MarketOrder` with `LimitOrder`.

### Code snippets

**`brotools/config.py`:**

```python
LIMIT_OFFSET_PCT = 0.005   # 0.5% above signal_close for marketable-limit entry
```

**`brotools/services.py` — `create_bracket_order`:**

```python
from brotools.config import LIMIT_OFFSET_PCT
from ib_async import LimitOrder

def create_bracket_order(
    qte: int = DEFAULT_QUANTITY,
    estimated_buy_price: float = 100.0,
) -> tuple:
    limit_price  = round(estimated_buy_price * (1 + LIMIT_OFFSET_PCT), 2)
    parent       = LimitOrder("BUY", qte, limit_price, tif="DAY", transmit=False)

    stop_price   = round(estimated_buy_price * STOP_LOSS_PCT, 2)
    stop_loss    = StopOrder("SELL", qte, stop_price, tif="GTC", transmit=False)

    target_price = round(estimated_buy_price * TAKE_PROFIT_PCT, 2)
    take_profit  = LimitOrder("SELL", qte, target_price, tif="GTC", transmit=True)

    return parent, stop_loss, take_profit
```

---

## 18. Add a max-concurrent-positions cap

### Problem summary

`place_orders_async` iterates over every row where `buy_signal == True` and
fires a bracket order for each. On a strong market day the scanner could return
10–20 valid signals. Without a cap, the system would simultaneously hold 20
long positions, concentrating risk and potentially exhausting buying power.

### Fix summary

Add `MAX_CONCURRENT_POSITIONS` to `config.py` and slice `df_signals` to that
many rows (ranked by strongest gap or signal quality) before building orders.

### Detailed explanation

1. **File to change:** `brotools/config.py` — add `MAX_CONCURRENT_POSITIONS = 3`.
2. **File to change:** `brotools/services.py` — `place_orders_async` —
   slice `df_signals` before `build_buy_orders`.
3. Optional: sort by `gap_percent` descending to take the strongest signals first.

### Code snippets

**`brotools/config.py`:**

```python
MAX_CONCURRENT_POSITIONS = 3   # max bracket orders to place in one session
```

**`brotools/services.py` — `place_orders_async`:**

```python
from brotools.config import MAX_CONCURRENT_POSITIONS

async def place_orders_async() -> None:
    ...
    df_signals = load_buy_signals(BUY_SIGNALS_FILE)

    if df_signals.empty:
        print("⚠️  No buy signals detected. Order placement skipped.")
        return

    # Cap at maximum concurrent positions, strongest gap first
    if "gap_percent" in df_signals.columns:
        df_signals = df_signals.sort_values("gap_percent", ascending=False)
    df_signals = df_signals.head(MAX_CONCURRENT_POSITIONS)

    print(f"📋 {len(df_signals)} signal(s) selected (cap: {MAX_CONCURRENT_POSITIONS})")
    order_items = build_buy_orders(df_signals)
    ...
```

---

## 19. Add a daily-loss limit / kill switch

### Problem summary

If the first few trades all hit their stop-loss, the system will keep placing
new orders for remaining signals with no awareness of cumulative losses. There
is no circuit breaker to halt trading after a bad start to the day.

### Fix summary

Add `MAX_DAILY_LOSS_USD` to `config.py`. Before placing each order, compute the
realized P&L from `4_trades.csv` for today. If losses already exceed the limit,
abort order placement and print a clear warning.

### Detailed explanation

1. **File to change:** `brotools/config.py` — add `MAX_DAILY_LOSS_USD`.
2. **File to change:** `brotools/services.py` — `place_orders_async` — add
   a pre-flight check that reads `TRADES_FILE` and sums `net_pnl` for today.
3. Add a helper `get_todays_pnl()` to `services.py` or `track_orders.py`.

### Code snippets

**`brotools/config.py`:**

```python
MAX_DAILY_LOSS_USD = 200.0   # halt new orders if today's realized loss exceeds this
```

**`brotools/services.py` — helper and pre-flight check:**

```python
from brotools.config import MAX_DAILY_LOSS_USD, TRADES_FILE

def get_todays_realized_pnl() -> float:
    """Sum net_pnl for trades completed today. Returns 0.0 if no trades file."""
    if not TRADES_FILE.exists():
        return 0.0
    df = pd.read_csv(TRADES_FILE)
    today = pd.Timestamp.now().date()
    if "parent_filled_at" not in df.columns or "net_pnl" not in df.columns:
        return 0.0
    df["date"] = pd.to_datetime(df["parent_filled_at"], errors="coerce").dt.date
    return df[df["date"] == today]["net_pnl"].sum()


async def place_orders_async() -> None:
    ...
    realized_pnl = get_todays_realized_pnl()
    if realized_pnl <= -MAX_DAILY_LOSS_USD:
        print(f"🛑 Daily loss limit hit (${realized_pnl:.2f}). "
              f"No new orders will be placed today.")
        return
    ...
```

---

## 20. Add a correlation / sector filter

### Problem summary

The scanner returns the top 50 % gainers with no sector awareness. On a
biotech catalyst day (e.g., an FDA announcement), 5–10 of the top signals
could be companies in the same sector. Buying all of them is effectively a
concentrated single-sector bet, not a diversified gap strategy.

### Fix summary

After generating buy signals, group by sector and keep at most
`MAX_SIGNALS_PER_SECTOR` per sector before passing to `place_orders_async`.
Use IBKR's `reqContractDetailsAsync` to retrieve the sector for each contract,
or maintain a simple lookup table from prior scan runs.

### Detailed explanation

1. **File to change:** `brotools/services.py` — after `load_buy_signals`.
2. Add `MAX_SIGNALS_PER_SECTOR = 1` to `config.py`.
3. Optionally store the sector in `2_buy_signals.csv` during the `signals`
   step by calling `reqContractDetailsAsync` in `save_data_async`.

### Code snippets

**`brotools/config.py`:**

```python
MAX_SIGNALS_PER_SECTOR = 1   # at most 1 signal per market sector
```

**`brotools/services.py` — filter after loading signals:**

```python
from brotools.config import MAX_SIGNALS_PER_SECTOR

async def place_orders_async() -> None:
    ...
    df_signals = load_buy_signals(BUY_SIGNALS_FILE)

    # Sector cap — requires a 'sector' column populated during getdata/signals
    if "sector" in df_signals.columns and MAX_SIGNALS_PER_SECTOR:
        df_signals = (df_signals
                      .sort_values("gap_percent", ascending=False)
                      .groupby("sector")
                      .head(MAX_SIGNALS_PER_SECTOR)
                      .reset_index(drop=True))
    ...
```

**Populating `sector` during `save_data_async`:**

```python
details = await ib.reqContractDetailsAsync(contract)
sector = details[0].industry if details else "Unknown"
df["sector"] = sector
```

---

## 21. Account for commissions and spread in signal logic

### Problem summary

The buy signal is evaluated purely on price momentum (gap % and green candles).
Commissions and bid/ask spread are never factored in during signal generation.
For a $10 stock with a 2 % stop ($0.20) and a $0.01 spread, transaction costs
consume a significant portion of the expected gain before the trade starts.

### Fix summary

Add a `MIN_EXPECTED_NET_GAIN_USD` threshold to `config.py`. In
`is_buy_signal`, compute the expected gross gain (`signal_close * TAKE_PROFIT_PCT - signal_close`)
and reject the signal if it does not exceed `MIN_EXPECTED_NET_GAIN_USD` plus
an estimated round-trip cost.

### Detailed explanation

1. **File to change:** `brotools/config.py` — add constants.
2. **File to change:** `brotools/strategies/gap_rise.py` — add a pre-flight
   rule or post-rule filter in `is_buy_signal`.

### Code snippets

**`brotools/config.py`:**

```python
ESTIMATED_COMMISSION_PER_SIDE = 0.005   # $0.005/share (IBKR tiered)
MIN_EXPECTED_NET_GAIN_USD     = 0.20    # minimum net gain per share after costs
```

**New rule function in `brotools/trading_rules.py`:**

```python
def check_min_net_gain(
    df_data: pd.DataFrame,
    take_profit_pct: float = 1.05,
    commission_per_side: float = 0.005,
    min_net_gain: float = 0.20,
) -> tuple[str, bool]:
    """Reject signals where expected net gain per share is below threshold."""
    entry  = df_data["signal_close"].iloc[-1] if "signal_close" in df_data.columns \
             else df_data["close"].iloc[-1]
    gross  = entry * take_profit_pct - entry
    net    = gross - 2 * commission_per_side
    return "min_net_gain_sufficient", net >= min_net_gain
```

Add it to the `rules` list in `Strategy.__init__`:

```python
from brotools.trading_rules import check_trading_window, check_gap_size, check_candles_up, check_min_net_gain

self.rules = [
    (check_trading_window, {"start_time": "09:30", "end_time": "09:45"}),
    (check_gap_size,       {"gap_threshold": 10.0}),
    (check_candles_up,     {"consecutive": 3}),
    (check_min_net_gain,   {"take_profit_pct": TAKE_PROFIT_PCT,
                            "commission_per_side": ESTIMATED_COMMISSION_PER_SIDE,
                            "min_net_gain": MIN_EXPECTED_NET_GAIN_USD}),
]
```

---

## 22. Make `check_candles_up` tolerant to first-bar timing

### Problem summary

`check_candles_up` in `trading_rules.py` verifies that the first regular-hours
bar starts at exactly `09:30`:

```python
opening_bar_time = df_regular_hours.index[0].strftime("%H:%M")
if opening_bar_time != start_rth:
    print(f"Skipping: RTH started at {opening_bar_time} instead of {start_rth}...")
    return rule_name, False
```

IBKR's data feed sometimes delivers the first bar timestamped at `09:31` due to
latency, processing delay, or a partial opening bar. This causes the rule to
silently return `False` for every valid signal on that day.

### Fix summary

Change the check from an exact equality to an approximate tolerance (e.g.,
accept the first bar if it falls within 2 minutes of `start_rth`), and use a
`logging.warning` instead of a print so the user knows the tolerance was
applied.

### Detailed explanation

1. **File to change:** `brotools/trading_rules.py` — `check_candles_up`.
2. Parse `start_rth` and the actual first-bar time as `datetime.time` objects.
3. Accept if the first bar is within `OPEN_BAR_TOLERANCE_MINS` minutes.
4. Add `OPEN_BAR_TOLERANCE_MINS = 2` to `config.py`.

### Code snippets

**Before:**

```python
opening_bar_time = df_regular_hours.index[0].strftime("%H:%M")
if opening_bar_time != start_rth:
    print(f"Skipping: RTH started at {opening_bar_time} instead of {start_rth} for {most_recent_date}.")
    return rule_name, False
```

**After:**

```python
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

OPEN_BAR_TOLERANCE_MINS = 2

opening_bar_dt = df_regular_hours.index[0]
expected_dt    = opening_bar_dt.replace(
    hour=int(start_rth.split(":")[0]),
    minute=int(start_rth.split(":")[1]),
    second=0, microsecond=0
)
delta = abs((opening_bar_dt - expected_dt).total_seconds()) / 60

if delta > OPEN_BAR_TOLERANCE_MINS:
    logger.warning(
        "RTH opened at %s instead of %s for %s — exceeds %d-min tolerance. Skipping.",
        opening_bar_dt.strftime("%H:%M"), start_rth, most_recent_date, OPEN_BAR_TOLERANCE_MINS
    )
    return rule_name, False

if delta > 0:
    logger.warning(
        "RTH bar slightly late (%s vs %s) for %s — within tolerance, continuing.",
        opening_bar_dt.strftime("%H:%M"), start_rth, most_recent_date
    )
```

---

## 23. Add a backtest harness

### Problem summary

The trading rules in `trading_rules.py` are pure functions that operate on
DataFrames, making them straightforward to run against historical data.
However, there is no backtest framework: no way to replay signals over past
days, compute win rate, profit factor, max drawdown, or validate the 10 % gap
threshold empirically.

### Fix summary

Add a `brotools/backtest.py` module and a `backtest` console script that loads
all `DATA/*.csv` files (or a specified folder), runs the full indicator and
signal pipeline day-by-day, and prints a summary table of hypothetical trades
with P&L metrics.

### Detailed explanation

1. **New file:** `brotools/backtest.py`.
2. **`pyproject.toml`** — add `backtest = "brotools.backtest:run_backtest"`.
3. The backtest loops over each unique date in the data, slices a 2-day window
   (prev day + current day) for each ticker, runs `add_indicators` and
   `is_buy_signal`, and if signalled, records the hypothetical entry at
   `signal_close`, stop at `signal_close * STOP_LOSS_PCT`, and target at
   `signal_close * TAKE_PROFIT_PCT`. It then looks forward to see which leg
   was hit first.

### Code snippets

**`brotools/backtest.py` (skeleton):**

```python
import glob
import pandas as pd
from pathlib import Path
from brotools.strategies.gap_rise import Strategy


def run_backtest(data_dir: str = "DATA") -> None:
    strategy = Strategy()
    results  = []

    for csv_path in sorted(Path(data_dir).glob("*.csv")):
        symbol = csv_path.stem
        if symbol.startswith(("1_", "2_", "3_", "4_")):
            continue  # skip pipeline output files

        df = pd.read_csv(csv_path, index_col="date", parse_dates=["date"])
        df["symbol"] = symbol
        unique_dates = sorted(df.index.date.tolist())

        for i, trade_date in enumerate(unique_dates):
            if i == 0:
                continue  # need at least one prior day

            # Slice prev day + trade day
            prev_date = unique_dates[i - 1]
            df_window = df[(df.index.date >= prev_date) &
                           (df.index.date <= trade_date)].copy()

            try:
                df_window = strategy.add_indicators(df_window)
                trace = strategy.is_buy_signal(df_window)
            except Exception:
                continue

            if not trace.get("buy_signal"):
                continue

            entry = trace["signal_close"]
            stop  = round(entry * 0.98, 2)
            tgt   = round(entry * 1.05, 2)

            # Look at bars after signal time on trade_date
            df_day = df[df.index.date == trade_date]
            sig_time = pd.Timestamp(trace["signal_time"])
            df_after = df_day[df_day.index > sig_time]

            exit_via = exit_price = None
            for _, bar in df_after.iterrows():
                if bar["low"] <= stop:
                    exit_via, exit_price = "stop", stop
                    break
                if bar["high"] >= tgt:
                    exit_via, exit_price = "target", tgt
                    break

            results.append({
                "date":       trade_date,
                "symbol":     symbol,
                "entry":      entry,
                "stop":       stop,
                "target":     tgt,
                "exit_via":   exit_via,
                "exit_price": exit_price,
                "pnl":        round(exit_price - entry, 4) if exit_price else None,
            })

    df_results = pd.DataFrame(results)
    if df_results.empty:
        print("No signals found in backtest data.")
        return

    print(df_results.to_string(index=False))
    wins = df_results[df_results["exit_via"] == "target"]
    loss = df_results[df_results["exit_via"] == "stop"]
    print(f"\nTotal trades : {len(df_results)}")
    print(f"Win rate     : {len(wins)/len(df_results)*100:.1f}%")
    print(f"Total P&L    : {df_results['pnl'].sum():.2f}")


if __name__ == "__main__":
    run_backtest()
```

**`pyproject.toml`:**

```toml
[project.scripts]
...
backtest = "brotools.backtest:run_backtest"
```

---

## 24. Change `IBKR_CLIENT_ID` away from `0`

### Problem summary

`config.py` sets `IBKR_CLIENT_ID = 0`. In IBKR's TWS, clientId `0` is treated
as a special value — TWS itself uses it for orders placed manually through the
TWS UI. Connecting an API client with id `0` can cause order-state confusion:
the API client may see TWS manual orders, and TWS may attribute API orders to
the manual session. Running two scripts simultaneously (e.g., `track` and
`orders`) both using id `0` will also cause a connection conflict.

### Fix summary

Change `IBKR_CLIENT_ID` to a non-zero value (e.g., `1`) and assign distinct
IDs to different tools (e.g., `1` for trading, `2` for tracking) via separate
config constants.

### Detailed explanation

1. **File to change:** `brotools/config.py`.
2. Replace `IBKR_CLIENT_ID = 0` with specific IDs per use case.
3. Update each module that connects to use the appropriate constant.

### Code snippets

**Before — `brotools/config.py`:**

```python
IBKR_CLIENT_ID = 0
```

**After:**

```python
IBKR_CLIENT_ID_TRADING  = 1   # used by scan, getdata, indicators, signals, orders
IBKR_CLIENT_ID_TRACKING = 2   # used by track
```

**`brotools/services.py`:**

```python
from brotools.config import IBKR_HOST, IBKR_PORT, IBKR_CLIENT_ID_TRADING as IBKR_CLIENT_ID
```

**`brotools/track_orders.py`:**

```python
from brotools.config import IBKR_HOST, IBKR_PORT, IBKR_CLIENT_ID_TRACKING as IBKR_CLIENT_ID
```

---

## 25. Add reconnection / heartbeat logic

### Problem summary

If TWS disconnects mid-session (network blip, TWS auto-restart, PC sleep),
the script raises an exception and exits. Server-side GTC stops protect the
open position, but:

- `track_orders.py` will not recover — it never retries after a disconnect.
- Any in-flight `place_orders_async` call will abort without finishing all orders.
- The user has no way to know which orders were placed before the disconnect.

### Fix summary

Wrap IB connection calls with a retry loop using exponential back-off. For
`track_orders.py` (which can run multiple times a day), a simple retry on
`ConnectionRefusedError` / `asyncio.TimeoutError` is sufficient. Use
`ib_async`'s `IB.connectedEvent` and `IB.disconnectedEvent` to log connection
state changes.

### Detailed explanation

1. **New helper** `connect_with_retry(ib, host, port, client_id, retries, delay)` —
   reusable across `services.py` and `track_orders.py`.
2. Replace all `await ib.connectAsync(...)` calls with the helper.
3. Subscribe to `ib.disconnectedEvent` to log when connection is lost.

### Code snippets

**`brotools/services.py` — reusable helper:**

```python
import asyncio
import logging

logger = logging.getLogger(__name__)

async def connect_with_retry(
    ib,
    host: str,
    port: int,
    client_id: int,
    retries: int = 3,
    delay: float = 5.0,
) -> None:
    """Connect to TWS with exponential back-off retries."""
    for attempt in range(1, retries + 1):
        try:
            await ib.connectAsync(host, port, clientId=client_id)
            ib.disconnectedEvent += lambda: logger.warning("⚠️  TWS disconnected.")
            logger.info("✅ Connected to TWS (attempt %d/%d)", attempt, retries)
            return
        except ConnectionRefusedError:
            if attempt == retries:
                raise
            logger.warning("Connection refused — retrying in %.1fs (attempt %d/%d)",
                           delay, attempt, retries)
            await asyncio.sleep(delay)
            delay *= 2
```

**Replace connection calls in `services.py` and `track_orders.py`:**

```python
# Before
await ib.connectAsync(IBKR_HOST, IBKR_PORT, clientId=IBKR_CLIENT_ID)

# After
await connect_with_retry(ib, IBKR_HOST, IBKR_PORT, IBKR_CLIENT_ID)
```

---

## 26. Replace manual five-command workflow with a single orchestrator

### Problem summary

The user must run five commands in order (`scan → getdata → indicators →
signals → orders`). If any step is run out of order or a prior step failed
silently, the next step uses stale or missing data — with no warning. There is
no `make` target or single entry point to run the whole morning pipeline safely.

### Fix summary

Add a `run_morning` console script that chains all five steps sequentially,
checks that each step succeeded before proceeding, and aborts with a clear
error if any step fails.

### Detailed explanation

1. **New function** `run_morning()` in `brotools/__main__.py`.
2. **`pyproject.toml`** — add `run_morning = "brotools.__main__:run_morning"`.
3. Each step calls the existing function and checks for success (non-empty
   output file, no exception).

### Code snippets

**`brotools/__main__.py`:**

```python
def run_morning() -> None:
    """Run the full morning pipeline: scan → getdata → indicators → signals → orders."""
    import sys
    steps = [
        ("scan",       get_scan),
        ("getdata",    get_data),
        ("indicators", add_indicators),
        ("signals",    get_signals),
        ("orders",     place_orders),
    ]
    for name, fn in steps:
        print(f"\n{'='*40}\n▶ Running: {name}\n{'='*40}")
        try:
            fn()
        except Exception as e:
            print(f"\n❌ Pipeline aborted at step '{name}': {e}")
            sys.exit(1)
    print("\n✅ Morning pipeline completed successfully.")
```

**`pyproject.toml`:**

```toml
run_morning = "brotools.__main__:run_morning"
```

---

## 27. Eliminate the wall-clock dependency with an async scheduler

### Problem summary

The README instructs: *"Run the scripts around 9:33."* This is a manual
wall-clock dependency — the user must watch the clock, open a terminal at
exactly the right time, and run the pipeline by hand. Missing the window by a
few minutes produces late signals that violate the `check_trading_window` rule.

### Fix summary

Extend `run_morning` (issue 26) with an optional `--wait` flag that sleeps
until 09:30 ET before starting the scan, then chains the remaining steps with
timed waits between `scan` and `getdata` (IBKR needs ~2 minutes to populate
the scanner).

### Detailed explanation

1. **File to change:** `brotools/__main__.py` — update `run_morning` to accept
   a `--wait` flag.
2. Use `zoneinfo.ZoneInfo("America/New_York")` (stdlib, Python 3.9+) for
   correct ET handling including daylight saving time.
3. Sleep until the target time, then execute the pipeline.

### Code snippets

**`brotools/__main__.py` — `run_morning` with scheduler:**

```python
import time
import argparse
from datetime import datetime
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

def run_morning() -> None:
    parser = argparse.ArgumentParser(prog="run_morning")
    parser.add_argument("--wait", action="store_true",
                        help="Sleep until 09:30 ET before starting.")
    parser.add_argument("--scan_time",  default="09:30",
                        help="HH:MM ET to run scan (default 09:30)")
    parser.add_argument("--entry_time", default="09:33",
                        help="HH:MM ET to run getdata→orders (default 09:33)")
    args = parser.parse_args()

    if args.wait:
        _sleep_until(args.scan_time)

    print("▶ Running: scan")
    get_scan()

    if args.wait:
        _sleep_until(args.entry_time)

    for name, fn in [("getdata", get_data), ("indicators", add_indicators),
                     ("signals", get_signals), ("orders", place_orders)]:
        print(f"▶ Running: {name}")
        fn()

    print("✅ Morning pipeline complete.")


def _sleep_until(hhmm: str) -> None:
    """Block until the given HH:MM in ET, today."""
    now = datetime.now(ET)
    h, m = map(int, hhmm.split(":"))
    target = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if target <= now:
        return   # already past target time
    wait_sec = (target - now).total_seconds()
    print(f"⏳ Waiting {wait_sec/60:.1f} min until {hhmm} ET...")
    time.sleep(wait_sec)
```

---

## 28. Add an explicit `--paper / --live` flag

### Problem summary

The only distinction between paper trading and live trading is the port number:
`7497` (TWS paper) vs `4002` (IB Gateway live). A user who edits the wrong line
in `config.py` — or forgets to switch back — will send real orders when
intending to paper trade (or vice versa). There is no safety prompt.

### Fix summary

Add `--paper` / `--live` flags to the `run_morning` orchestrator (and
individual commands). Let the flag override the port from `config.py` and
print a clear confirmation banner before placing any order.

### Detailed explanation

1. **File to change:** `brotools/config.py` — add `IBKR_PORT_PAPER` and
   `IBKR_PORT_LIVE`.
2. **File to change:** `brotools/__main__.py` — parse `--paper / --live` in
   `run_morning` and `place_orders`, set the port accordingly.
3. Before calling `place_orders_async`, print a confirmation banner that
   includes the port and mode and pauses for 3 seconds so the user can abort
   with Ctrl+C.

### Code snippets

**`brotools/config.py`:**

```python
IBKR_PORT_PAPER = 7497   # TWS paper trading
IBKR_PORT_LIVE  = 4002   # IB Gateway live trading
IBKR_PORT       = IBKR_PORT_PAPER   # default to paper for safety
```

**`brotools/__main__.py` — `place_orders` with mode flag:**

```python
import time as _time

def place_orders() -> None:
    parser = argparse.ArgumentParser(prog="orders")
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument("--paper", action="store_true", help="Use TWS paper port 7497")
    mode_group.add_argument("--live",  action="store_true", help="Use IB Gateway live port 4002")
    args = parser.parse_args()

    from brotools import config as cfg
    if args.live:
        cfg.IBKR_PORT = cfg.IBKR_PORT_LIVE
        mode_label = "🔴 LIVE TRADING"
    else:
        cfg.IBKR_PORT = cfg.IBKR_PORT_PAPER
        mode_label = "🟡 PAPER TRADING"

    print(f"\n{'='*50}")
    print(f"  MODE  : {mode_label}")
    print(f"  PORT  : {cfg.IBKR_PORT}")
    print(f"  Starting in 3 seconds — press Ctrl+C to abort")
    print(f"{'='*50}\n")
    _time.sleep(3)

    asyncio.run(place_orders_async())
```

---

## 29. Move off CSV-as-database

### Problem summary

All pipeline state (`1_scan_results.csv`, `2_buy_signals.csv`,
`3_placed_orders.csv`, `4_trades.csv`) is stored as flat CSV files. This means:

- Two simultaneous runs corrupt files with interleaved writes.
- There is no schema validation — a wrong column name or type silently produces
  `NaN` values downstream.
- Appending rows (`mode="a"`) duplicates headers if done incorrectly.
- `pd.read_csv` on a partially written file raises an exception with no
  transaction safety.

### Fix summary

Replace CSV state files with a single SQLite database (`DATA/brotools.db`).
SQLite is file-based (no server), supports concurrent reads, serializes writes
atomically via transactions, and enforces column types. Use `pandas.to_sql` and
`pd.read_sql` for DataFrame integration.

### Detailed explanation

1. **New file:** `brotools/db.py` — database initialization and helpers.
2. Replace all `pd.read_csv / df.to_csv` calls in `services.py`,
   `track_orders.py`, and `__main__.py` with SQL equivalents.
3. Keep CSV export as an optional reporting step, not the primary storage.

### Code snippets

**`brotools/db.py` — schema and helpers:**

```python
import sqlite3
from pathlib import Path
import pandas as pd

DB_PATH = Path("DATA/brotools.db")


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(exist_ok=True)
    return sqlite3.connect(DB_PATH)


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS scan_results (
                rank INTEGER, symbol TEXT, conId INTEGER,
                localSymbol TEXT, tradingClass TEXT,
                scanned_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS buy_signals (
                symbol TEXT, buy_signal INTEGER,
                gap_percent REAL, signal_close REAL,
                signal_time TEXT, created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS placed_orders (
                symbol TEXT, submitted_at TEXT,
                parent_order_id INTEGER, parent_status TEXT, parent_filled_at TEXT,
                sl_order_id INTEGER,     sl_status TEXT,     sl_filled_at TEXT,
                tp_order_id INTEGER,     tp_status TEXT,     tp_filled_at TEXT
            );
            CREATE TABLE IF NOT EXISTS trades (
                symbol TEXT, parent_order_id INTEGER UNIQUE,
                entry_price REAL, exit_price REAL, quantity INTEGER,
                exit_via TEXT, net_pnl REAL, total_commission REAL,
                parent_filled_at TEXT, created_at TEXT DEFAULT (datetime('now'))
            );
        """)


def write_df(df: pd.DataFrame, table: str, if_exists: str = "append") -> None:
    with get_connection() as conn:
        df.to_sql(table, conn, if_exists=if_exists, index=False)


def read_df(table: str, where: str = "") -> pd.DataFrame:
    with get_connection() as conn:
        query = f"SELECT * FROM {table}"
        if where:
            query += f" WHERE {where}"
        return pd.read_sql(query, conn)
```

---

## 30. Raise on errors instead of printing them

### Problem summary

Throughout the pipeline, errors are handled by printing `❌ ...` and then
continuing or returning `None`. The shell exit code is always `0` (success),
so scripts that call `brotools` commands — or a future `run_morning`
orchestrator — cannot detect that a step failed. A partial pipeline run
produces stale output files that feed incorrect data into the next step.

### Fix summary

Replace silent `return` / `return None` after errors with `raise SystemExit(1)`
(for user-facing CLI entry points) or `raise` (for library functions called
by the CLI). This ensures the shell exit code is non-zero on failure and the
`run_morning` orchestrator (issue 26) can abort early.

### Detailed explanation

1. **CLI entry points** in `__main__.py` (`get_scan`, `get_data`, etc.) should
   catch exceptions from the async functions and call `sys.exit(1)`.
2. **Library functions** in `services.py`, `track_orders.py` should re-raise
   instead of swallowing (see also issue 3).
3. Keep informational `print`/`logger` calls before raising so the user sees
   the reason.

### Code snippets

**Before — `services.py` `get_report_async`:**

```python
except Exception as e:
    print(f"❌ Error during scan: {e}")
# returns None implicitly
```

**After — re-raise so caller knows:**

```python
except Exception as e:
    print(f"❌ Error during scan: {type(e).__name__}: {e}")
    raise
```

**Before — `__main__.py` `get_scan`:**

```python
def get_scan():
    with Strategy() as strategy:
        scan_result = asyncio.run(get_report_async(strategy))
        if scan_result is not None:
            scan_result.to_csv("DATA/1_scan_results.csv", index=False)
            print(f"Scan report saved {len(scan_result)} prospects.")
```

**After — explicit exit code on failure:**

```python
import sys

def get_scan():
    with Strategy() as strategy:
        try:
            scan_result = asyncio.run(get_report_async(strategy))
        except Exception as e:
            print(f"❌ scan failed: {e}")
            sys.exit(1)
    if scan_result is None or scan_result.empty:
        print("❌ Scan returned no results — aborting.")
        sys.exit(1)
    scan_result.to_csv("DATA/1_scan_results.csv", index=False)
    print(f"✅ Scan saved {len(scan_result)} prospects to DATA/1_scan_results.csv")
```

Apply the same pattern to `get_data`, `add_indicators`, `get_signals`, and
`place_orders` so the `run_morning` orchestrator (issue 26) can rely on
non-zero exit codes to abort the pipeline immediately on the first failure.
