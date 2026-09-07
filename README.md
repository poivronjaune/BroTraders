# BroTraders

BroTraders is a Python learning project for exploring automated trading workflows with the Interactive Brokers (IBKR) API. It is intended for study, experimentation, and paper-trading practice.

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
- Start with the simulator and offline tests when possible.
- Review the generated signals and orders before allowing any paper orders.

The default TWS port in this project is `7497`, which is the usual paper-trading port. Port numbers can be changed in IBKR installations, so verify the setting in TWS/Gateway and in [`brotoolsv2/config.py`](brotoolsv2/config.py). The project must not be used with a live-trading connection.

## Current status

BroTraders v2 is an alpha-stage learning project. It currently includes:

- The `brotoolsv2` bot-session scaffold for IBKR connectivity, strategy discovery, watchlists, risk management, order management, and trading logs.
- An IBKR protocol simulator for offline connection testing.
- Automated tests for selected components.

The v2 implementation is still under development. Its main execution flow contains simulated phases and placeholder behavior; it is not a distributable package or a production trading system.

## Requirements

- Python 3.12 or newer
- Windows, macOS, or Linux with the appropriate Python commands
- An IBKR paper-trading account for broker-connected workflows
- Trader Workstation (TWS) or IB Gateway configured for API access
- Appropriate IBKR market-data permissions for the requested data

Real-time market data generally requires a funded IBKR account and the relevant market-data subscriptions. Without those subscriptions, IBKR may provide delayed quotes (often approximately 15 minutes behind real time), and some instruments or data types may be unavailable.

Cryptocurrency trading requires additional IBKR account configuration and trading permissions. Availability, supported products, funding requirements, and any required crypto-service account setup vary by jurisdiction and account type; do not assume that a standard paper-trading account is enabled for crypto. Consult IBKR's current requirements before attempting any crypto workflow.

The simulator in [`ibkrmock/IBKR_Simulator.py`](ibkrmock/IBKR_Simulator.py) uses only the Python standard library and can be used without an IBKR account for limited connection testing.

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

Install the test dependencies when needed:

```text
py -m pip install -e ".[test]"
```

On macOS/Linux, use `python -m pip` instead of `py -m pip`.

## IBKR configuration

The main configuration is in [`brotoolsv2/config.py`](brotoolsv2/config.py):

- `IBKR_HOST` — normally `127.0.0.1`
- `IBKR_PORT` — normally `7497` for TWS paper trading
- `IBKR_CLIENT_ID` — the API client identifier
- Risk and safety limits, including per-trade risk, maximum concurrent positions, maximum equity exposure, and the daily-loss kill switch

Enable API connections in TWS or IB Gateway and make sure the host, port, and client ID agree with this file. Do not store passwords, account credentials, API tokens, or private account information in the repository.

## Running the v2 bot session

After confirming that the connection is to the paper account, start the current v2 entry point with:

```text
py -m brotoolsv2
```

The current v2 entry point connects to TWS, reports the planned execution phases, generates simulated bars, and disconnects. Strategy discovery, recurring scans, warm-up, signal evaluation, order placement, and fill handling are currently represented as scaffold phases or simulated behavior. Do not interpret the current output as evidence that a live trading strategy is ready.

## Offline simulator

The simulator can be started without TWS:

```text
py ibkrmock\IBKR_Simulator.py
```

It listens by default on `127.0.0.1:7497` and implements only a limited portion of the IBKR protocol. It currently supports connection/startup behavior and empty responses for selected account and order queries. It does **not** yet implement the market scanner, historical or live bars, market data snapshots, order placement, order status, or fills. Unsupported requests may wait for a response.

Do not run the simulator on the same port as TWS.

## Project layout

The existing folders are intentionally preserved:

| Folder | Purpose |
| --- | --- |
| `brotoolsv2/` | Current experimental trading bot and IBKR integration |
| `ibkrmock/` | IBKR simulator and market-data fetching utilities |
| `tests/` | Automated tests |
| `TODO/` | Development notes |
| `DATA/` | Local/generated market data; not required to be committed |
| `LOGS/` | Local runtime logs |
| `TMP/` | Local temporary files and development notes |

Generated data, logs, virtual environments, and test caches are ignored by Git. Do not publish account-specific data, order history, credentials, or private logs.

## Running tests

Run the offline test suite:

```text
py -m pytest
```

The tests are intended to run without connecting to TWS or placing orders. Passing tests do not prove that a trading strategy is safe or profitable.

## Scanner notes

Recurring scanner support is part of the planned v2 execution model but is not implemented in the current bot-session entry point. When it is enabled, scanner results will depend on market hours, IBKR permissions, market-data availability, and the configured price, volume, market-capitalization, exchange, and market-data filters.

## Data sources

The utilities in `ibkrmock/` can retrieve market data from external public GitHub repositories. Downloaded data is stored locally and is not part of the core source code. Check the source repository's terms and license before using or redistributing downloaded data.

## License

BroTraders is provided under the [MIT License](LICENSE).
