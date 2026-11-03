"""Rich logs with query strings, exception values and ORM debug data removed."""

import logging
import logging.config
from datetime import UTC, datetime

from rich.console import Console
from rich.logging import RichHandler
from rich.text import Text


class SafeLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if (
            record.name == "uvicorn.access"
            and isinstance(record.args, tuple)
            and len(record.args) == 5
        ):
            args = list(record.args)
            args[2] = str(args[2]).split("?", 1)[0]
            record.args = tuple(args)
        if record.exc_info and record.exc_info[1] is not None:
            error = RuntimeError(
                f"{type(record.exc_info[1]).__name__}: error details redacted"
            )
            record.exc_info = (RuntimeError, error, record.exc_info[2])
        return True


def utc_time(value: datetime) -> Text:
    return Text(value.astimezone(UTC).strftime("%H:%M:%S UTC"))


def rich_handler() -> RichHandler:
    handler = RichHandler(
        console=Console(stderr=True),
        show_path=False,
        markup=False,
        rich_tracebacks=True,
        tracebacks_show_locals=False,
        log_time_format=utc_time,
    )
    handler.addFilter(SafeLogFilter())
    return handler


def log_config(level: str = "info") -> dict:
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {"message": {"format": "%(message)s"}},
        "handlers": {
            "rich": {
                "()": "tapkofon.logging_config.rich_handler",
                "formatter": "message",
            }
        },
        "root": {"handlers": ["rich"], "level": level.upper()},
        "loggers": {
            "uvicorn": {
                "handlers": ["rich"],
                "level": level.upper(),
                "propagate": False,
            },
            "uvicorn.error": {
                "handlers": [],
                "level": level.upper(),
                "propagate": True,
            },
            "uvicorn.access": {
                "handlers": ["rich"],
                "level": "INFO",
                "propagate": False,
            },
            **{
                name: {"handlers": [], "level": "WARNING", "propagate": True}
                for name in ("telethon", "tortoise", "aiosqlite", "httpx2", "httpcore2")
            },
        },
    }


def configure_logging(level: str) -> None:
    logging.config.dictConfig(log_config(level))
