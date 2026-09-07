# BroTraders v1 (`brotools`)

BroTraders v1 is a Python learning project for exploring automated trading workflows with the Interactive Brokers (IBKR) API. It is intended for study, experimentation, and paper-trading practice through the `brotools` package.

> **API note:** IBKR provides an official [TWS API](https://www.interactivebrokers.com/docs/tws-api/doc/introduction) and documentation. BroTraders does not use the official API client directly; it uses the [`ib_async`](https://github.com/ib-api-reloaded/ib_async) Python wrapper instead.

## Important safety warning

**This project MUST be used only with an Interactive Brokers paper-trading account.**

**Do not use BroTraders with a live trading account.** Automated trading can submit orders without an additional manual confirmation, and software errors, incorrect configuration, unexpected market conditions, connection problems, or misunderstood strategies can cause substantial financial losses.

This project is educational software. It is not financial advice, is not production-ready, and provides no guarantee of correctness or profitability. You are responsible for protecting your account and for every action taken by your TWS or IB Gateway connection.

Before running the project:

- Create and use an IBKR paper-trading account.
- Configure Trader Workstation (TWS) or IB Gateway for API access.
- Confirm that the application is connected to the paper account.
- Never change the connection to a live-trading port or live account.
- Review the generated signals and orders before allowing any paper orders.

The default TWS port in this project is `7497`, which is the usual paper-trading port. Port numbers can be changed in IBKR installations, so verify the setting in TWS/Gateway and in [`brotools/config.py`](brotools/config.py). The project must not be used with a live-trading connection.

## Current status

BroTraders v1 is an alpha-stage learning project. The `brotools` package currently provides:

- Market scanning through IBKR
- Historical price-data retrieval
- Technical-indicator calculation
- Strategy-based buy-signal generation
- Bracket-order placement
- Order tracking and data-cleaning utilities

The package is not production-ready or intended for live trading.

## Requirements

- Python 3.12 or newer
- Windows, macOS, or Linux with the appropriate Python commands
- An IBKR paper-trading account for broker-connected workflows
- Trader Workstation (TWS) or IB Gateway configured for API access
- Appropriate IBKR market-data permissions for the requested data

Real-time market data generally requires a funded IBKR account and the relevant market-data subscriptions. Without those subscriptions, IBKR may provide delayed quotes (often approximately 15 minutes behind real time), and some instruments or data types may be unavailable.

Cryptocurrency trading requires additional IBKR account configuration and trading permissions. Availability, supported products, funding requirements, and any required crypto-service account setup vary by jurisdiction and account type; do not assume that a standard paper-trading account is enabled for crypto. Consult IBKR's current requirements before attempting any crypto workflow.

## Installation

Create and activate a virtual environment, then install the project in editable mode:

### Windows PowerShell

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install --upgrade pip
py -m pip install -e .
```

### macOS/Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

On macOS/Linux, use `python -m pip` instead of `py -m pip`.

## IBKR configuration

The main configuration is in [`brotools/config.py`](brotools/config.py):

- `IBKR_HOST` — normally `127.0.0.1`
- `IBKR_PORT` — normally `7497` for TWS paper trading
- `IBKR_CLIENT_ID` — the API client identifier
- `STRATEGY_FILE` — the strategy selected by the current implementation

Enable API connections in TWS or IB Gateway and make sure the host, port, and client ID agree with this file. Do not store passwords, account credentials, API tokens, or private account information in the repository.

## Paper-trading workflow

Run these commands only after confirming that the connection is to the paper account:

| Command | Purpose | Typical output |
| --- | --- | --- |
| `scan` | Request a scanner report and find candidate stocks | `DATA/1_scan_results.csv` |
| `getdata` | Retrieve price data for symbols in the scan result | `DATA/<ticker>.csv` files |
| `indicators` | Add strategy indicators to price data | Updated ticker CSV files |
| `signals` | Generate buy signals from the configured strategy | `DATA/2_buy_signals.csv` |
| `orders` | Submit bracket orders for generated signals | Order records and logs |
| `track` | Track order status and execution information | Logs and tracking output |
| `clean` | Clean historical local data | Local data changes |
| `run_live` | Run the live-trading workflow code | **Do not use with a live account; paper account only** |

The usual sequence is:

```text
scan -> getdata -> indicators -> signals -> orders -> track
```

The scanner workflow is time-sensitive. The current strategy is designed around the market open; the existing implementation commonly runs the scan around 9:30 and subsequent steps around 9:33 Eastern Time. Results depend on market hours, IBKR permissions, connectivity, and the selected scanner settings.

The `orders` command can submit orders automatically. Treat it as potentially dangerous even when using paper trading, and inspect configuration and generated signals before running it.

## Project layout

| Folder | Purpose |
| --- | --- |
| `brotools/` | v1 trading workflow and IBKR integration |
| `DATA/` | Local/generated market data |
| `LOGS/` | Local runtime logs |
| `TODO/` | Development notes |

Generated data, logs, virtual environments, and temporary files should not be published. Do not publish account-specific data, order history, credentials, or private logs.

## Scanner notes

The strategy uses an IBKR scanner subscription. For example, `TOP_PERC_GAIN` returns rankings based on the current time, while `HIGH_OPEN_GAP` may return no results before the market opens. Scanner results also depend on the configured price, volume, market-capitalization, exchange, and market-data filters.

## License

BroTraders is provided under the [MIT License](LICENSE).
