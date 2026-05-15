"""Logging configuration."""
import logging
import logging.handlers
import os
from pathlib import Path
import json
from datetime import datetime

DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
LOGS_DIR = DATA_DIR / "logs"
SENSITIVE_KEYS = ("token", "secret", "authorization", "bearer")


def redact(value: str) -> str:
    """Redact obvious tokens/secrets from log text."""
    text = str(value)
    for key in SENSITIVE_KEYS:
        if key in text.lower():
            return "[redacted sensitive log message]"
    return text


class JSONFormatter(logging.Formatter):
    """Format logs as JSON."""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact(record.getMessage()),
        }

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data)


def setup_logging(
    app_name: str = "ha-print-monitor",
    json_output: bool = False,
    log_level: str = "INFO",
):
    """Setup logging for the application.

    Args:
        app_name: Application name for logs
        json_output: Use JSON formatter if True
    """
    # Create logs directory
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    # Create logger
    logger = logging.getLogger()
    level = getattr(logging, log_level.upper(), logging.INFO)
    logger.setLevel(level)

    # Remove existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)

    if json_output:
        console_formatter = JSONFormatter()
    else:
        console_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # File handler (rotating)
    log_file = LOGS_DIR / f"{app_name}.log"
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
    )
    file_handler.setLevel(level)

    if json_output:
        file_formatter = JSONFormatter()
    else:
        file_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    # Suppress noisy loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)

    return logger
