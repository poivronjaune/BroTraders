import os
import json 
import pandas as pd 
from datetime import datetime

class Strategy:
    def __init__(self):
        self.name = "Top Percent Gainers"   
        self.gap_treshold = 10.0  
    
    def set_active_strategy(self, filename="DATA/strategy.json"):
        strategy = {
            "name": self.name,
            "chosen_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "scanner" : {
                "sub.numberOfRows": 50,
                "sub.scanCode": 'TOP_PERC_GAIN',
                "sub.locationCode": 'STK.US.MAJOR',
                "sub.abovePrice": 10,
                "sub.belowPrice": 200,
                "sub.aboveVolume": 100000,
                "sub.marketCapAbove": 300
            },
            "params": {
                "gap_threshold": self.gap_treshold
            }    
        }
        
        with open(filename, "w") as f:
            json.dump(strategy, f, indent=4)    
        

    def load_active_strategy(self, filename="DATA/strategy.json"):
        if not os.path.exists(filename):
            # Raising an error here allows the calling function to know exactly what failed
            raise FileNotFoundError(f"Strategy configuration file NOT found at: {os.path.abspath(filename)}")
        
        
        with open(filename, "r") as f:
            strategy_json = json.load(f)
        print(strategy_json)
        
        return strategy_json


        
if __name__ == "__main__":
    s = Strategy()
    # s.set_active_strategy()    
    s.load_active_strategy()