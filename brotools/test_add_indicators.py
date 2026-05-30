import pandas as pd

from brotools.strategies.gap_rise import Strategy

if __name__ == "__main__":
    strategy = Strategy()
    tickers = pd.read_csv("DATA/1_scan_results.csv")["symbol"].tolist()
    with Strategy() as strategy:
        for ticker in tickers:
            df_data = pd.read_csv(
                f"DATA/{ticker}.csv", 
                index_col="date",  # Sets this column as the row labels (index)
                parse_dates=["date"]  # Forces pandas to convert strings to true Timestamp objects
            )     
            
            df_data = strategy.add_indicators(df_data)
            df_data.to_csv(f'DATA/{ticker}.csv')
            print(df_data.head())        

    