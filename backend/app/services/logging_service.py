"""Logging service: Python logging with RotatingFileHandler."""
import os
import logging
from logging.handlers import RotatingFileHandler
from app.config import Config


_loggers = {}


def _resolve_level():
    """Resolve Config.LOG_LEVEL into a logging level int.

    Falls back to INFO when the configured value is unknown, so a typo in
    LOG_LEVEL never crashes startup.
    """
    level = logging.getLevelName(str(getattr(Config, "LOG_LEVEL", "INFO")).upper())
    return level if isinstance(level, int) else logging.INFO


def _setup_logging():
    """Initialize logging configuration."""
    log_dir = Config.LOG_DIR
    os.makedirs(log_dir, exist_ok=True)
    level = _resolve_level()

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Module-specific loggers
    modules = ["api", "ai", "generation", "auth", "middleware", "call_log", "analytics"]

    for module in modules:
        logger = logging.getLogger(f"testcase.{module}")
        # Level must be set before the duplicate-handler short-circuit below,
        # otherwise re-initialization would leave the previous level in place.
        logger.setLevel(level)

        # Avoid duplicate handlers
        if logger.handlers:
            continue

        handler = RotatingFileHandler(
            os.path.join(log_dir, f"{module}.log"),
            maxBytes=Config.LOG_MAX_BYTES,
            backupCount=Config.LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    # Combined app logger (all modules; level = Config.LOG_LEVEL)
    app_logger = logging.getLogger("testcase")
    app_logger.setLevel(level)
    if not app_logger.handlers:
        combined_handler = RotatingFileHandler(
            os.path.join(log_dir, "app.log"),
            maxBytes=Config.LOG_MAX_BYTES,
            backupCount=Config.LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
        combined_handler.setFormatter(formatter)
        app_logger.addHandler(combined_handler)

    # Dedicated error handler on the root testcase logger — captures ERROR+
    # from ALL sub-loggers (api, ai, middleware, etc.) into error.log.
    # No separate testcase.error logger is needed; get_error_logger() returns
    # the root logger, and the ERROR-level handler filters appropriately.
    if not any(getattr(h, "_error_log", False) for h in app_logger.handlers):
        eh = RotatingFileHandler(
            os.path.join(log_dir, "error.log"),
            maxBytes=Config.LOG_MAX_BYTES,
            backupCount=Config.LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
        eh.setFormatter(formatter)
        eh.setLevel(logging.ERROR)
        eh._error_log = True  # marker to avoid duplicate registration
        app_logger.addHandler(eh)

    # Mark initialization done so get_logger() doesn't re-run setup on every call
    _loggers["__ready__"] = True


def get_logger(name):
    """Get a module-specific logger."""
    if not _loggers:
        _setup_logging()
    return logging.getLogger(f"testcase.{name}")


def get_app_logger():
    """Get the combined app logger."""
    if not _loggers:
        _setup_logging()
    return logging.getLogger("testcase")


def get_error_logger():
    """Get the error logger (writes ERROR+ to error.log via root logger)."""
    if not _loggers:
        _setup_logging()
    return logging.getLogger("testcase")
