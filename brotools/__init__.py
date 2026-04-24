
def choose_strategy():
    print("Choose a strategy to activate:")
    print("1. High Open Gap Strategy - Works only at market open")
    print("2. Top Percent Gains - Works all day")
    
    choice = input("Enter the number of the strategy you want to run: ")
    
    if choice == '1':
        from brotools.strategy_high_open_gap import Strategy
    elif choice == '2':
        from brotools.strategy_top_perc_gain import Strategy
    else:
        print("Invalid choice. Please select a valid strategy number.")
        return
    
    strategy_filename = "DATA/strategy.json"
    strategy = Strategy()
    Strategy_name = strategy.name
    strategy.set_active_strategy(filename=strategy_filename)

    print(f"\nStrategy '{Strategy_name}' has been set as the active strategy. See file '{strategy_filename}' for details.")

    