import sys
import pandas as pd

def report():
    print('Running report command...')
    

def fetch():
    print('Running fetch command...')  
    

def signals():
    print('Running signals command...')
    

def trade():
    print('Running trade command...')
    

if __name__ == "__main__":
    # Grab command line arguments
    # If no arguments, run the default scan and signal generation
    
    if len(sys.argv) == 1:
        print("Specify command : report, fetch, signals, trade")# Run default scan and signal generation
        sys.exit()
        
    command = sys.argv[1].lower()
    if command == "report":
        report()
    elif command == "fetch":
        fetch()
    elif command == "signals":
        signals()
    elif command == "trade":
        trade()
    else:
        print(f"Unknown command: {command}")
        print("Available commands: report, fetch, signals, trade")
        sys.exit()
    