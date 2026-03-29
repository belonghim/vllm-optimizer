"""
Structured JSON Logging Configuration

Provides a JSON formatter for structured logging output.
Configure via environment variables:
  LOG_LEVEL  — log level (default: INFO)
  LOG_FORMAT — "json" for structured JSON, anything else for plain text (default: text)
"""

import json
import logging
import os


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict = {
            "timestamp": self.formatTime(record, datefmt="%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "name": record.name,
        }
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, ensure_ascii=False)


def configure_logging() -> None:
    """Configure root logger.

    Uses JSON format when LOG_FORMAT=json, otherwise plain text.
    This replaces any existing handlers on the root logger.
    """
    log_level = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)
    log_format = os.getenv("LOG_FORMAT", "text").lower()

    handler = logging.StreamHandler()
    if log_format == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )

    logging.root.handlers.clear()
    logging.root.addHandler(handler)
    logging.root.setLevel(log_level)
