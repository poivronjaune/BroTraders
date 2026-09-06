import argparse
import csv
import io
import logging
import os
import random
import sys
import time
import requests
import urllib3

import calendar
import pandas as pd
from datetime import date, timedelta
from logging.handlers import TimedRotatingFileHandler

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

log = logging.getLogger(__name__)


def setup_logging() -> None:
    os.makedirs(LOG_DIR, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s  %(levelname)-8s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    file_handler = TimedRotatingFileHandler(
        filename=os.path.join(LOG_DIR, "fetchdata.log"),
        when="h",
        backupCount=24,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(fmt)
    logging.basicConfig(level=logging.INFO, handlers=[file_handler, stream_handler])

# ---------------------------------------------------------------------------
# Step 1 — Constants & Configuration
# ---------------------------------------------------------------------------
BASE_ORG_URL = "https://raw.githubusercontent.com/MapleFrogStudio/"

OUTPUT_DIR = "C:/Workspace/PoivronJaune-GitHub/BroTraders/ibkrmock/Data/"
LOG_DIR    = "C:/Workspace/PoivronJaune-GitHub/BroTraders/ibkrmock/FetchFromGithub/logs/"
QUEUE_FILE = "C:/Workspace/PoivronJaune-GitHub/BroTraders/ibkrmock/FetchFromGithub/queue.csv"

EXCHANGE_PREFIXES = {
    "amex":  [1],
    "nasdaq": [1, 2, 3, 4, 5],
    "nyse":  [1, 2, 3],
    "tsx":   [1, 2],
    "tsxv":  [1, 2, 3, 4],
}

THROTTLE_MIN = 2   # seconds
THROTTLE_MAX = 25  # seconds

# Batch flushing configuration to minimize slow external drive writes
SAVE_EVERY_N_FILES = 10 

LABEL_WIDTH = 22   # aligns colons in all console output — must be >= longest label used in printing

# ANSI color codes
COLOR_RESET  = "\033[0m"
COLOR_GREEN  = "\033[32m"
COLOR_RED    = "\033[31m"
COLOR_YELLOW = "\033[33m"
COLOR_CYAN   = "\033[36m"

EXPECTED_COLUMNS = {"Datetime", "Ticker", "Open", "High", "Low", "Close", "Volume"}
KEEP_COLUMNS     = ["Datetime", "Ticker", "Open", "High", "Low", "Close", "Volume"]

# Explicit dtypes to speed up CSV parsing in Pandas
CSV_DTYPES = {
    "Ticker": "category",
    "Open": "float32",
    "High": "float32",
    "Low": "float32",
    "Close": "float32",
    "Volume": "int64",
}


def print_info(label: str, value: str, color: str = "") -> None:
    colored_label = f"{color}{label:<{LABEL_WIDTH}}{COLOR_RESET}" if color else f"{label:<{LABEL_WIDTH}}"
    print(f"{colored_label}: {value}")


# ---------------------------------------------------------------------------
# Step 2 — URL builder helpers
# ---------------------------------------------------------------------------
def repo_name(year: int, month: int) -> str:
    return f"DATA-{year:04d}-{month:02d}"


def repo_probe_url(year: int, month: int) -> str:
    return f"https://github.com/MapleFrogStudio/DATA-{year:04d}-{month:02d}"


def raw_file_url(year: int, month: int, exchange: str, n: int, day: int) -> str:
    return (
        f"{BASE_ORG_URL}DATA-{year:04d}-{month:02d}/refs/heads/main/"
        f"{exchange}{n}-{year:04d}-{month:02d}-{day:02d}.csv"
    )


# ---------------------------------------------------------------------------
# Step 4 — Month iterator
# ---------------------------------------------------------------------------
def iter_months(start_date: date, end_date: date):
    year, month = start_date.year, start_date.month
    end_year, end_month = end_date.year, end_date.month
    while (year, month) <= (end_year, end_month):
        yield year, month
        month += 1
        if month > 12:
            month = 1
            year += 1


# ---------------------------------------------------------------------------
# Step 2b — Build fetch queue for a confirmed month
# ---------------------------------------------------------------------------
def build_fetch_queue(year: int, month: int, start_dt: date, end_dt: date) -> list[str]:
    last_day    = calendar.monthrange(year, month)[1]
    window_start = max(date(year, month, 1), start_dt)
    window_end   = min(date(year, month, last_day), end_dt)

    urls = []
    current = window_start
    while current <= window_end:
        if current.weekday() < 5:  # Mon=0 .. Fri=4; skip Sat=5, Sun=6
            for exchange, numbers in EXCHANGE_PREFIXES.items():
                for n in numbers:
                    urls.append(raw_file_url(year, month, exchange, n, current.day))
        current += timedelta(days=1)
    return urls


# ---------------------------------------------------------------------------
# Phase 2c — Queue persistence (In-memory batch writing)
# ---------------------------------------------------------------------------
STATE_PLANNED   = "planned"
STATE_COMPLETED = "completed"
STATE_ERROR     = "error"


def write_queue(queue: dict[str, str]) -> None:
    """Overwrites queue file on disk with the current in-memory status."""
    with open(QUEUE_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        for url, state in queue.items():
            writer.writerow([url, state])


def load_queue() -> dict[str, str]:
    queue = {}
    with open(QUEUE_FILE, newline="", encoding="utf-8") as f:
        for row in csv.reader(f):
            if len(row) == 2:
                queue[row[0]] = row[1]
    return queue


def _probe_and_build_queue(session: requests.Session, start_dt: date, end_dt: date) -> dict[str, str]:
    """Scan GitHub repos for the date range, build a fresh queue dict, write it to disk."""
    all_urls = []
    for year, month in iter_months(start_dt, end_dt):
        if repo_exists(session, year, month):
            all_urls.extend(build_fetch_queue(year, month, start_dt, end_dt))
    queue = {url: STATE_PLANNED for url in all_urls}
    if queue:
        write_queue(queue)
        print_info("Queue created", f"{len(queue)} files planned", COLOR_CYAN)
    return queue


# ---------------------------------------------------------------------------
# Step 3 — Repo existence check
# ---------------------------------------------------------------------------
def repo_exists(session: requests.Session, year: int, month: int) -> bool:
    url = repo_probe_url(year, month)
    print_info("Probing data location", url)
    try:
        response = session.get(url, verify=False)
        if response.status_code == 200:
            print_info("Repo detected", repo_name(year, month), COLOR_GREEN)
            log.info("Repo detected: %s", repo_name(year, month))
            return True
        elif response.status_code == 404:
            print_info("Repo not found", repo_name(year, month), COLOR_RED)
            log.info("Repo not found: %s", repo_name(year, month))
            return False
        else:
            print_info("Unexpected status", f"{response.status_code} for {repo_name(year, month)}", COLOR_YELLOW)
            log.warning("Unexpected status %s for %s", response.status_code, repo_name(year, month))
            return False
    except requests.exceptions.RequestException as e:
        print_info("Network error", str(e), COLOR_RED)
        log.error("Network error probing %s: %s", repo_name(year, month), e)
        return False


# ---------------------------------------------------------------------------
# Phase 3 — Per-file pipeline
# ---------------------------------------------------------------------------
def fetch_csv(session: requests.Session, url: str) -> pd.DataFrame | None:
    try:
        response = session.get(url, verify=False)
        if response.status_code != 200:
            print_info("Skipped", f"HTTP {response.status_code} — {url}", COLOR_YELLOW)
            log.warning("Skipped HTTP %s: %s", response.status_code, url)
            return None
        
        # Fast byte decoding into Pandas with predefined dtypes
        df = pd.read_csv(io.BytesIO(response.content), dtype=CSV_DTYPES)
        
        missing = EXPECTED_COLUMNS - set(df.columns)
        if missing:
            print_info("Skipped", f"Missing columns {missing} — {url}", COLOR_YELLOW)
            log.warning("Skipped missing columns %s: %s", missing, url)
            return None
        log.info("Fetched %d rows: %s", len(df), url)
        return df
    except requests.exceptions.RequestException as e:
        print_info("Network error", str(e), COLOR_RED)
        log.error("Network error fetching %s: %s", url, e)
        return None
    except Exception as e:
        print_info("Parse error", str(e), COLOR_RED)
        log.error("Parse error fetching %s: %s", url, e)
        return None


def transform(df: pd.DataFrame) -> pd.DataFrame:
    df = df[KEEP_COLUMNS].copy()
    # Explicit datetime formatting avoids expensive auto-inference parsing
    df["Datetime"] = pd.to_datetime(df["Datetime"], format="%Y-%m-%d %H:%M:%S", errors="coerce")
    return df


def flush_ticker_buffers(ticker_buffers: dict[str, list[pd.DataFrame]], output_dir: str) -> None:
    """Fast write: Appends buffered data to the slow external disk without reading prior contents."""
    os.makedirs(output_dir, exist_ok=True)
    
    for ticker, dfs in ticker_buffers.items():
        if not dfs:
            continue
            
        combined_new = pd.concat(dfs, ignore_index=True)
        path = os.path.join(output_dir, f"{ticker}.csv")
        file_exists = os.path.exists(path)
        
        # Append without header if file exists
        combined_new.to_csv(
            path, 
            mode='a' if file_exists else 'w', 
            header=not file_exists, 
            index=False
        )
        
    ticker_buffers.clear()


def parse_args():
    parser = argparse.ArgumentParser(
        description="Fetch and consolidate GitHub raw CSV market data into per-ticker files.",
        epilog=(
            "Examples:\n"
            "  fetchdata --start 2025-04-01 --end 2025-04-30\n"
            "  fetchdata --start 2025-01-01 --end 2026-04-30"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--start", required=True, metavar="YYYY-MM-DD", help="First date to fetch (inclusive)")
    parser.add_argument("--end",   required=True, metavar="YYYY-MM-DD", help="Last date to fetch (inclusive)")
    parser.add_argument("--output", metavar="FOLDER", default=OUTPUT_DIR, help=f"Output folder to save per-ticker CSVs (default: {OUTPUT_DIR})")

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    args = parser.parse_args()

    try:
        start_dt = date.fromisoformat(args.start)
    except ValueError:
        parser.error(f"Invalid --start date '{args.start}' — expected YYYY-MM-DD")

    try:
        end_dt = date.fromisoformat(args.end)
    except ValueError:
        parser.error(f"Invalid --end date '{args.end}' — expected YYYY-MM-DD")

    if start_dt > end_dt:
        parser.error(f"--start {start_dt} must not be after --end {end_dt}")

    return start_dt, end_dt, args.output


def main():
    setup_logging()
    start_dt, end_dt, output_dir = parse_args()
    print_info("Output folder", output_dir, COLOR_CYAN)

    session = requests.Session()

    if os.path.exists(QUEUE_FILE):
        queue = load_queue()
        n_planned   = sum(1 for s in queue.values() if s == STATE_PLANNED)
        n_completed = sum(1 for s in queue.values() if s == STATE_COMPLETED)
        n_error     = sum(1 for s in queue.values() if s == STATE_ERROR)
        print_info("Queue found", f"{n_planned} planned, {n_completed} completed, {n_error} errors")

        answer = input("[K] Keep and resume   [S] Start over   > ").strip().upper()
        if answer == "S":
            os.remove(QUEUE_FILE)
            queue = _probe_and_build_queue(session, start_dt, end_dt)
        else:
            print_info("Resuming queue", f"{n_planned} planned, {n_error} errors", COLOR_CYAN)
    else:
        queue = _probe_and_build_queue(session, start_dt, end_dt)

    if not queue:
        print_info("Nothing to fetch", "No repos found for the given date range", COLOR_YELLOW)
        return

    pending = [url for url, state in queue.items() if state != STATE_COMPLETED]
    print_info("Pending downloads", str(len(pending)), COLOR_CYAN)

    # In-memory accumulator for ticker DataFrames
    ticker_buffers = {}
    processed_count = 0

    try:
        for url in pending:
            print_info("Downloading", url, COLOR_CYAN)
            df = fetch_csv(session, url)
            
            if df is not None:
                df = transform(df)
                print_info("Rows fetched", str(len(df)), COLOR_GREEN)
                
                # Accumulate data in-memory by ticker
                for ticker, rows in df.groupby("Ticker", observed=False):
                    if ticker not in ticker_buffers:
                        ticker_buffers[ticker] = []
                    ticker_buffers[ticker].append(rows)
                    
                    print_info("Saved", f"{ticker}  {len(rows)} new rows", COLOR_GREEN)
                    log.info("Saved %s: %d new rows", ticker, len(rows))
                
                queue[url] = STATE_COMPLETED
            else:
                queue[url] = STATE_ERROR
                print_info("No data", url, COLOR_YELLOW)
                log.warning("No data for: %s", url)

            processed_count += 1

            # Periodically write accumulated batch data & queue status to disk
            if processed_count % SAVE_EVERY_N_FILES == 0:
                print_info("Batch Flush", f"Writing memory buffers to disk...", COLOR_CYAN)
                flush_ticker_buffers(ticker_buffers, output_dir)
                write_queue(queue)

            delay = random.uniform(THROTTLE_MIN, THROTTLE_MAX)
            print_info("Throttle", f"{delay:.1f}s", COLOR_CYAN)
            log.info("Throttle %.1fs", delay)
            time.sleep(delay)

    finally:
        # Final flush to write remaining in-memory data when script finishes or interrupted
        if ticker_buffers:
            print_info("Final Flush", "Flushing remaining buffers to disk...", COLOR_CYAN)
            flush_ticker_buffers(ticker_buffers, output_dir)
        write_queue(queue)
        session.close()


if __name__ == "__main__":
    main()