from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler


_LOGGER_CACHE: dict[str, logging.Logger] = {}


def _resolve_log_level() -> int:
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    return getattr(logging, level_name, logging.INFO)


def _resolve_log_file() -> str:
    return os.getenv("LOG_FILE", "")


def _build_formatter() -> logging.Formatter:
    return logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def get_logger(name: str = "zju_activity_calendar") -> logging.Logger:
    cached = _LOGGER_CACHE.get(name)
    if cached is not None:
        return cached

    logger = logging.getLogger(name)
    logger.setLevel(_resolve_log_level())
    logger.propagate = False

    if not logger.handlers:
        formatter = _build_formatter()

        console_handler = logging.StreamHandler()
        console_handler.setLevel(logger.level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        log_file = _resolve_log_file()
        if log_file:
            file_handler = RotatingFileHandler(f"{log_file}.log", maxBytes=1024 * 1024, backupCount=7)
            file_handler.setLevel(logger.level)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)

    _LOGGER_CACHE[name] = logger
    return logger


def _format_context(**context) -> str:
    parts = []
    for key, value in context.items():
        if value is None:
            continue
        text = str(value).replace("\n", " ").strip()
        if not text:
            continue
        parts.append(f"{key}={text}")
    return " ".join(parts)


def log_event(level: str, message: str, **context) -> None:
    logger = get_logger()
    line = message
    context_line = _format_context(**context)
    if context_line:
        line = f"{message} | {context_line}"
    getattr(logger, level.lower(), logger.info)(line)
