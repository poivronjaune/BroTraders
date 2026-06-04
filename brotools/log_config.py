import logging 
import logging.handlers
from pathlib import Path 

LOG_DIR = Path("LOGS")
LOG_FILE = LOG_DIR / "brotraders.log"

def configure_logging(level: str = "INFO") -> None:
    LOG_DIR.mkdir(exist_ok=True)
    
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        '%(asctime)s,%(levelname)s,%(name)s,"%(message)s"', 
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console = logging.StreamHandler()
    console.setLevel(getattr(logging, level.upper(), logging.INFO))
    console.setFormatter(fmt)

    # Rotating file handler
    file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=1_000_000, backupCount=5, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)

    # Add handlers to the root logger
    root.addHandler(console)
    root.addHandler(file_handler)