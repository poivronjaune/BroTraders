# datacleaning.py
import os
import sys

import pandas as pd
from datetime import datetime

# No logger since this script is for manuel use only

# --- DEFAULT FALLBACK BOUNDARIES ---
START_BOUND = "2026-05-28 04:00:00"

def clean_historical_data():
    scan_results_path = "DATA/1_scan_results.csv"
    
    # 1. Verify the scan file exists before starting
    if not os.path.exists(scan_results_path):
        print(f"❌ Aborted: '{scan_results_path}' could not be found.")
        return

    # 2. Extract command-line flags
    args = sys.argv[1:]
    end_bound_input = None
    
    if "-end_bound" in args:
        try:
            # Find the index of the flag and extract everything following it
            flag_idx = args.index("-end_bound")
            # Join trailing items in case the user omitted quotes (e.g., -end_bound 2026-05-29 20:00:00)
            end_bound_input = " ".join(args[flag_idx + 1 :]).strip()
        except IndexError:
            pass

    # 3. Guard clause: If flag is missing or empty, print example usage and exit
    if not end_bound_input:
        current_dt_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print("❌ Error: Missing required parameter '-end_bound'.")
        print("\n💡 Usage Example:")
        print(f'   clean -end_bound "{current_dt_str}"')
        return

    # Extract the target tickers from scan results
    df_scan = pd.read_csv(scan_results_path)
    tickers = df_scan["symbol"].tolist()
    
    try:
        # Convert boundary inputs to pure, timezone-naive Timestamps
        start_ts = pd.to_datetime(START_BOUND).tz_localize(None)
        end_ts = pd.to_datetime(end_bound_input).tz_localize(None)
    except Exception as e:
        print(f"❌ Datetime Parsing Error: Could not convert '{end_bound_input}' to a clean timestamp. ({e})")
        print('   Expected format: "YYYY-MM-DD HH:MM:SS"')
        return
    
    print(f"\n" + "="*50)
    print(f"🧹 Starting Timezone-Agnostic Data Purification Pipeline")
    print(f"   Filtering range: [{start_ts}] to [{end_ts}]")
    print("="*50)

    cleaned_count = 0
    
    for ticker in tickers:
        file_path = f"DATA/{ticker}.csv"
        
        if not os.path.exists(file_path):
            print(f"⚠️  Skipped: Data file for {ticker} does not exist at {file_path}")
            continue
            
        try:
            # Load the file, ensuring 'date' is assigned as the index
            df_data = pd.read_csv(file_path, index_col="date", parse_dates=["date"])
            original_row_count = len(df_data)
            
            # Create a temporary timezone-naive index copy just for the comparison mask
            naive_index = df_data.index.tz_localize(None)
            
            # Filter rows using the naive index mask (keeps original data rows untouched)
            df_cleaned = df_data[(naive_index >= start_ts) & (naive_index <= end_ts)]
            
            # Save the clean slice back to CSV (keeping index=True for the 'date' column)
            df_cleaned.to_csv(file_path, index=True)
            
            rows_removed = original_row_count - len(df_cleaned)
            print(f"✅ {ticker:5} -> Trimmed {rows_removed:,} rows. (Remaining: {len(df_cleaned):,})")
            cleaned_count += 1
            
        except Exception as e:
            print(f"❌ Error processing file for {ticker}: {e}")

    print("-"*50 + f"\n🎉 Done! Successfully cleaned {cleaned_count}/{len(tickers)} historical files.")

if __name__ == "__main__":
    clean_historical_data()