from __future__ import annotations

import logging
import re
import sys
from logging.handlers import TimedRotatingFileHandler

from hlr_reconciliation.models.config import LoggingConfig


class SecretRedactionFilter(logging.Filter):
    PATTERN = re.compile(r"(?i)(password|passwd|pwd|secret|token|uri)=([^,\s]+)")

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = self.PATTERN.sub(r"\1=***", str(record.msg))
        return True


def configure_logging(config: LoggingConfig) -> logging.Logger:
    logger = logging.getLogger("hlr_reconciliation")
    if logger.handlers:
        return logger

    level = getattr(logging, config.log_level.upper(), logging.INFO)
    logger.setLevel(level)
    logger.propagate = False
    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s [%(name)s:%(funcName)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    redaction_filter = SecretRedactionFilter()

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(level)
    stream_handler.setFormatter(formatter)
    stream_handler.addFilter(redaction_filter)
    logger.addHandler(stream_handler)

    config.log_directory.mkdir(parents=True, exist_ok=True)
    file_handler = TimedRotatingFileHandler(
        filename=config.log_directory / config.log_filename,
        when=config.rotation_when,
        interval=config.rotation_interval,
        backupCount=config.retention_count,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    file_handler.addFilter(redaction_filter)
    logger.addHandler(file_handler)
    return logger
