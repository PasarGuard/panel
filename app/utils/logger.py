import logging
import logging.config
from copy import copy
from typing import Any
from urllib.parse import unquote

import click

from config import (
    ECHO_SQL_QUERIES,
    LOG_BACKUP_COUNT,
    LOG_FILE_PATH,
    LOG_LEVEL,
    LOG_MAX_BYTES,
    LOG_ROTATION_ENABLED,
    LOG_ROTATION_INTERVAL,
    LOG_ROTATION_UNIT,
    SAVE_LOGS_TO_FILE,
)

DEFAULT_DATE_FMT = "%Y-%m-%d %H:%M:%S"
LEVEL_STYLES: dict[int, dict[str, Any]] = {
    logging.CRITICAL: {"fg": "red", "bold": True},
    logging.ERROR: {"fg": "red", "bold": True},
    logging.WARNING: {"fg": "yellow", "bold": True},
    logging.INFO: {"fg": "green", "bold": True},
    logging.DEBUG: {"fg": "blue", "bold": True},
}


class LevelPrefixFormatter(logging.Formatter):
    def __init__(self, fmt: str | None = None, datefmt: str | None = None, use_colors: bool | None = True):
        self.use_colors = True if use_colors is None else use_colors
        super().__init__(fmt=fmt, datefmt=datefmt)

    def formatMessage(self, record: logging.LogRecord) -> str:
        recordcopy = copy(record)
        level_style = LEVEL_STYLES.get(recordcopy.levelno, {})
        prefix = recordcopy.levelname
        if self.use_colors and level_style:
            prefix = click.style(prefix, **level_style)
        recordcopy.levelprefix = prefix
        return super().formatMessage(recordcopy)


class CustomLoggingFormatter(LevelPrefixFormatter):
    def formatMessage(self, record: logging.LogRecord) -> str:
        recordcopy = copy(record)
        nameprefix = record.name.capitalize()
        if self.use_colors:
            nameprefix = click.style(nameprefix, fg="blue")
        recordcopy.nameprefix = nameprefix
        return super().formatMessage(recordcopy)


class CustomAccessFormatter(LevelPrefixFormatter):
    def _format_status_code(self, status_code: int) -> str:
        if not self.use_colors:
            return str(status_code)
        if status_code < 200:
            return click.style(str(status_code), fg="blue")
        if status_code < 300:
            return click.style(str(status_code), fg="green")
        if status_code < 400:
            return click.style(str(status_code), fg="cyan")
        if status_code < 500:
            return click.style(str(status_code), fg="yellow")
        return click.style(str(status_code), fg="red")

    def formatMessage(self, record: logging.LogRecord) -> str:
        recordcopy = copy(record)

        try:
            client_addr, method, full_path, http_version, status_code = recordcopy.args  # type: ignore[misc]
        except Exception:
            return super().formatMessage(record)

        status_code = int(status_code)
        request_line = f"{method} {full_path} HTTP/{http_version}"
        if self.use_colors:
            request_line = click.style(request_line, bold=True)

        recordcopy.client_addr = client_addr
        recordcopy.request_line = request_line
        recordcopy.status_code = self._format_status_code(status_code)
        recordcopy.process_time = getattr(recordcopy, "process_time", "-")

        return super().formatMessage(recordcopy)


class RequireProcessTimeFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return getattr(record, "process_time", None) is not None


LOGGING_CONFIG: dict[str, Any] = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "()": LevelPrefixFormatter,
            "fmt": "%(levelprefix)s %(asctime)s - %(message)s",
            "datefmt": DEFAULT_DATE_FMT,
            "use_colors": None,
        },
        "custom": {
            "()": CustomLoggingFormatter,
            "fmt": "%(levelprefix)s %(asctime)s - %(nameprefix)s - %(message)s",
            "datefmt": DEFAULT_DATE_FMT,
            "use_colors": None,
        },
        "access": {
            "()": CustomAccessFormatter,
            "fmt": '%(levelprefix)s %(asctime)s - %(client_addr)s - "%(request_line)s" %(status_code)s - %(process_time)s',
            "datefmt": DEFAULT_DATE_FMT,
            "use_colors": None,
        },
    },
    "handlers": {
        "default": {"class": "logging.StreamHandler", "formatter": "default", "stream": "ext://sys.stdout"},
        "access": {"class": "logging.StreamHandler", "formatter": "access", "stream": "ext://sys.stdout"},
        "custom": {"class": "logging.StreamHandler", "formatter": "custom", "stream": "ext://sys.stdout"},
    },
    "loggers": {
        "uvicorn": {"handlers": ["default"], "level": LOG_LEVEL, "propagate": False},
        "uvicorn.error": {"handlers": ["default"], "level": LOG_LEVEL, "propagate": False},
        "uvicorn.access": {"handlers": ["access"], "level": LOG_LEVEL, "propagate": False},
        "_granian": {"handlers": ["default"], "level": LOG_LEVEL, "propagate": False},
        "granian.access": {"handlers": ["access"], "level": LOG_LEVEL, "propagate": False},
    },
}

LOGGING_CONFIG.setdefault("filters", {})
LOGGING_CONFIG["filters"]["require_process_time"] = {"()": RequireProcessTimeFilter}
LOGGING_CONFIG["loggers"]["uvicorn.access"].setdefault("filters", [])
LOGGING_CONFIG["loggers"]["uvicorn.access"]["filters"].append("require_process_time")

if SAVE_LOGS_TO_FILE:
    if LOG_ROTATION_ENABLED:
        LOGGING_CONFIG["handlers"]["file"] = {
            "class": "logging.handlers.TimedRotatingFileHandler",
            "formatter": "default",
            "filename": LOG_FILE_PATH,
            "interval": LOG_ROTATION_INTERVAL,
            "when": LOG_ROTATION_UNIT,
            "backupCount": LOG_BACKUP_COUNT,
        }
    else:
        LOGGING_CONFIG["handlers"]["file"] = {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "default",
            "filename": LOG_FILE_PATH,
            "maxBytes": LOG_MAX_BYTES,
            "backupCount": LOG_BACKUP_COUNT,
        }
    LOGGING_CONFIG["loggers"]["uvicorn"]["handlers"].append("file")
    LOGGING_CONFIG["loggers"]["uvicorn.access"]["handlers"].append("file")


logging.config.dictConfig(LOGGING_CONFIG)


def get_logger(name: str = "uvicorn.error") -> logging.Logger:
    if not LOGGING_CONFIG["loggers"].get(name):
        handlers = ["custom"]
        if SAVE_LOGS_TO_FILE:
            handlers.append("file")
        LOGGING_CONFIG["loggers"][name] = {
            "handlers": handlers,
            "level": LOG_LEVEL,
            "propagate": False,
        }
        logging.config.dictConfig(LOGGING_CONFIG)

    logger = logging.getLogger(name)
    return logger


if ECHO_SQL_QUERIES:
    _ = get_logger("sqlalchemy.engine")


class EndpointFilter(logging.Filter):
    def __init__(self, excluded_endpoints: list[str]):
        self.excluded_endpoints = excluded_endpoints

    def filter(self, record: logging.LogRecord) -> bool:
        if record.args and len(record.args) >= 3:
            path = unquote(record.args[2])
            return path not in self.excluded_endpoints
        return True
