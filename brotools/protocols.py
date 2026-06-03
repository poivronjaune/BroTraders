from typing import Protocol
from ib_async import ScannerSubscription

class StrategyProtocol(Protocol):
    """Minimal contract that services.py relies on."""
    def scanner(self) -> ScannerSubscription: ...

    