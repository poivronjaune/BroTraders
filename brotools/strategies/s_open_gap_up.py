import os
import json 
import pandas as pd 
from datetime import datetime

class Strategy_Open_Gap_Up:
    def __init__(self):
        self.name = "Open Gap Strategy"   
        self.gap_treshold = 10.0  
    
    def set_active_strategy(self, filename="DATA/strategy.json"):
        '''Dynamically create a strategy.json file to activate this strategy so other commands can work with it'''
        strategy = {
            "name": self.name,
            "chosen_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "scanner" : {
                "sub.numberOfRows": 50,
                "sub.scanCode": 'HIGH_OPEN_GAP',
                "sub.locationCode": 'STK.US.MAJOR',
                "sub.abovePrice": 50,
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
        '''Normalised stragy.json loading to get parameters for commands. This should be called before any command.'''
        if not os.path.exists(filename):
            # Raising an error here allows the calling function to know exactly what failed
            raise FileNotFoundError(f"Strategy configuration file NOT found at: {os.path.abspath(filename)}")
        
        
        with open(filename, "r") as f:
            strategy_json = json.load(f)
        print(strategy_json)
        
        return strategy_json

