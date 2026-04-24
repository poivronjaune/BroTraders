from pathlib import Path
from brotools.strategies.s_open_gap_up import Strategy_Open_Gap_Up

def get_strategy_list():
    # Define the directory
    strat_dir = Path("brotools/strategies")
    
    # 1. glob("s_*") finds everything starting with s_
    # 2. .stem gets the filename without the extension (e.g., .py)
    # 3. is_file() ensures we don't accidentally pick up folders
    strategies = [f.stem for f in strat_dir.glob("s_*") if f.is_file()]

    return strategies

__all__ = [
    Strategy_Open_Gap_Up
]    