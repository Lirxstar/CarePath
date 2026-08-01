import json
import logging
from contextvars import ContextVar, Token
from datetime import UTC, datetime
from typing import Any, TextIO

_REQUEST_ID: ContextVar[str] = ContextVar("carepath_request_id", default="-")
_ALLOWED_EXTRA_FIELDS = (
    "component",
    "route",
    "status_code",
    "duration_ms",
    "error_code",
    "error_class",
    "provider",
)


def set_request_id(request_id: str) -> Token[str]:
    return _REQUEST_ID.set(request_id)


def reset_request_id(token: Token[str]) -> None:
    _REQUEST_ID.reset(token)


def get_request_id() -> str:
    return _REQUEST_ID.get()


class CarePathJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        event: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": get_request_id(),
        }
        for field in _ALLOWED_EXTRA_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                event[field] = value
        return json.dumps(event, ensure_ascii=False, separators=(",", ":"))


class CarePathStreamHandler(logging.StreamHandler[TextIO]):
    """Identifies the handler managed by CarePath logging configuration."""


def configure_logging(level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger("carepath")
    logger.setLevel(level)
    logger.propagate = False

    if not any(isinstance(handler, CarePathStreamHandler) for handler in logger.handlers):
        carepath_handler = CarePathStreamHandler()
        carepath_handler.setFormatter(CarePathJsonFormatter())
        logger.addHandler(carepath_handler)

    for installed_handler in logger.handlers:
        if isinstance(installed_handler, CarePathStreamHandler):
            installed_handler.setLevel(level)

    # Uvicorn's default access logger includes the raw path and query string.
    # CarePath emits a minimized route-template event in its middleware instead.
    logging.getLogger("uvicorn.access").disabled = True
    return logger
