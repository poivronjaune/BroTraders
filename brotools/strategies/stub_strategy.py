# brotools/strategies/gap_fall.py
from ib_async import ScannerSubscription

class Strategy:
    def __init__(self):
        # Only scafolding to test protocols and strategy definitions
        self.name = "Stub Strategy"

    def __enter__(self):
        print(f"Opening connection to {self.name}.")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        print(f"Closing connection to {self.name} safely.")

    def scanner(self) -> ScannerSubscription:
        sub = ScannerSubscription()
        sub.numberOfRows = 50
        sub.instrument = "STK"
        sub.locationCode = "STK.US.MAJOR"
        sub.scanCode = "TOP_PERC_LOSE"
        return sub