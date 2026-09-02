import logging
import sys
from pathlib import Path
from datetime import datetime


class ColorFormatter(logging.Formatter):
    COLORS = {
        "DEBUG": "\033[36m",
        "INFO": "\033[32m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
        "CRITICAL": "\033[35m",
    }
    RESET = "\033[0m"

    def format(self, record):
        color = self.COLORS.get(record.levelname, "")
        record.levelname = f"{color}{record.levelname}{self.RESET}"
        return super().format(record)


def get_logger(name):
    logger = logging.getLogger(name)

    if not logger.handlers:
        logger.setLevel(logging.DEBUG)

        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_formatter = ColorFormatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            datefmt="%H:%M:%S"
        )
        console_handler.setFormatter(console_formatter)

        log_dir = Path("data/logs")
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"bot_{datetime.now().strftime('%Y_%m_%d')}.log"

        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
        )
        file_handler.setFormatter(file_formatter)

        logger.addHandler(console_handler)
        logger.addHandler(file_handler)

    return logger
