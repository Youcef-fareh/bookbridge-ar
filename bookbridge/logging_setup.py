"""Centralised logging for BookBridge.

Every run writes two rotating log files inside ``<data_dir>/logs``:

* ``bookbridge.log`` – everything at the configured level (INFO by default)
* ``errors.log``      – only warnings/errors and tracebacks

The files are what users can attach to a bug report. The desktop UI also reads
``bookbridge.log`` for its **Logs & Diagnostics** page, so no separate store is
needed.

The module also installs hooks for:

* uncaught exceptions in the main thread (``sys.excepthook``)
* uncaught exceptions in worker threads (``threading.excepthook``)
* Qt messages (``qInstallMessageHandler``)
* Python warnings (``logging.captureWarnings``)

Set ``BOOKBRIDGE_LOG_LEVEL=DEBUG`` before launching for verbose output.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import platform
import sys
import tempfile
import threading
from pathlib import Path
from typing import Optional

from bookbridge.config.settings import settings

LOG_FILENAME = "bookbridge.log"
ERROR_LOG_FILENAME = "errors.log"

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

MAX_LOG_BYTES = 2_000_000
MAX_LOG_BACKUPS = 5
MAX_ERROR_BYTES = 1_000_000
MAX_ERROR_BACKUPS = 3

_logger = logging.getLogger("bookbridge")
_state_lock = threading.Lock()
_configured = False
_log_dir: Optional[Path] = None
_log_path: Optional[Path] = None
_error_log_path: Optional[Path] = None
_qt_handler_installed = False


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def get_log_dir() -> Path:
    """Return the directory holding the log files."""
    return _log_dir or (settings.logs_dir)


def get_log_path() -> Path:
    """Return the path of the main log file."""
    return _log_path or (get_log_dir() / LOG_FILENAME)


def get_error_log_path() -> Path:
    """Return the path of the warning/error-only log file."""
    return _error_log_path or (get_log_dir() / ERROR_LOG_FILENAME)


def resolve_level(value: object = None) -> int:
    """Turn a level name/int into a logging level, defaulting to INFO."""
    if isinstance(value, int):
        return value
    name = str(value or os.getenv("BOOKBRIDGE_LOG_LEVEL") or "INFO").upper()
    return getattr(logging, name, logging.INFO)


def setup_logging(
    log_dir: Optional[Path] = None,
    level: object = None,
    *,
    force: bool = False,
    install_hooks: bool = True,
) -> Path:
    """Configure file/console logging and install crash hooks.

    Returns the path to the main log file. Safe to call more than once; the
    second call is a no-op unless ``force`` is given (useful in tests).
    """
    global _configured, _log_dir, _log_path, _error_log_path

    with _state_lock:
        if _configured and not force:
            return get_log_path()

        if force:
            _remove_our_handlers()

        target_dir = Path(log_dir) if log_dir else settings.logs_dir
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            fallback = Path(tempfile.gettempdir()) / "bookbridge-logs"
            fallback.mkdir(parents=True, exist_ok=True)
            print(f"BookBridge: cannot use log directory {target_dir} ({exc}); "
                  f"falling back to {fallback}", file=sys.stderr)
            target_dir = fallback

        _log_dir = target_dir
        _log_path = target_dir / LOG_FILENAME
        _error_log_path = target_dir / ERROR_LOG_FILENAME

        level_value = resolve_level(level)
        formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)

        root = logging.getLogger()
        root.setLevel(logging.DEBUG)

        file_handler = logging.handlers.RotatingFileHandler(
            _log_path,
            maxBytes=MAX_LOG_BYTES,
            backupCount=MAX_LOG_BACKUPS,
            encoding="utf-8",
            delay=True,
        )
        file_handler.setLevel(level_value)
        file_handler.setFormatter(formatter)
        _tag(file_handler)
        root.addHandler(file_handler)

        error_handler = logging.handlers.RotatingFileHandler(
            _error_log_path,
            maxBytes=MAX_ERROR_BYTES,
            backupCount=MAX_ERROR_BACKUPS,
            encoding="utf-8",
            delay=True,
        )
        error_handler.setLevel(logging.WARNING)
        error_handler.setFormatter(formatter)
        _tag(error_handler)
        root.addHandler(error_handler)

        # A windowed PyInstaller build has no stdout/stderr; avoid logging errors.
        if sys.stderr is not None:
            console = logging.StreamHandler(sys.stderr)
            console.setLevel(min(level_value, logging.INFO))
            console.setFormatter(formatter)
            _tag(console)
            root.addHandler(console)

        logging.captureWarnings(True)

        # Third-party chatter that would hide our own messages.
        for noisy in ("httpx", "httpcore", "urllib3", "asyncio", "PySide6"):
            logging.getLogger(noisy).setLevel(logging.WARNING)

        _configured = True

        _logger.info("Logging to %s", _log_path)
        _logger.info("Error log: %s", _error_log_path)

    if install_hooks:
        install_exception_hooks()
        install_qt_message_handler()
    return get_log_path()


def log_environment() -> None:
    """Log versions and paths that help reproduce a problem."""
    _logger.info("-" * 78)
    _logger.info(
        "BookBridge %s starting | frozen=%s",
        getattr(settings, "version", "unknown"),
        bool(getattr(sys, "frozen", False)),
    )
    _logger.info(
        "Platform: %s %s (%s) | Python %s",
        platform.system(),
        platform.release(),
        platform.machine(),
        platform.python_version(),
    )
    _logger.info("Executable: %s", sys.executable)
    _logger.info("Data dir: %s", settings.data_dir)
    _logger.info("Database: %s", settings.db_path)
    _logger.info("Log file: %s", get_log_path())
    _logger.info("-" * 78)


# ---------------------------------------------------------------------------
# Crash hooks
# ---------------------------------------------------------------------------


def install_exception_hooks() -> None:
    """Route uncaught main-thread/thread exceptions into the log file."""
    if getattr(install_exception_hooks, "_installed", False):
        return
    install_exception_hooks._installed = True  # type: ignore[attr-defined]

    previous_hook = sys.excepthook

    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            previous_hook(exc_type, exc_value, exc_traceback)
            return
        logging.getLogger("bookbridge.crash").critical(
            "Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback)
        )
        previous_hook(exc_type, exc_value, exc_traceback)

    sys.excepthook = handle_exception

    previous_thread_hook = threading.excepthook

    def handle_thread_exception(args: threading.ExceptHookArgs) -> None:
        if issubclass(args.exc_type, SystemExit):
            previous_thread_hook(args)
            return
        logging.getLogger("bookbridge.crash").critical(
            "Uncaught exception in thread %r",
            getattr(args.thread, "name", "unknown"),
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    threading.excepthook = handle_thread_exception


def install_qt_message_handler() -> None:
    """Forward Qt warnings/critical messages to the Python log."""
    global _qt_handler_installed
    if _qt_handler_installed:
        return
    try:
        from PySide6.QtCore import QtMsgType, qInstallMessageHandler
    except Exception:  # pragma: no cover - PySide6 is optional for tests
        return

    logger = logging.getLogger("bookbridge.qt")

    levels = {
        QtMsgType.QtDebugMsg: logging.DEBUG,
        QtMsgType.QtInfoMsg: logging.INFO,
        QtMsgType.QtWarningMsg: logging.WARNING,
        QtMsgType.QtCriticalMsg: logging.ERROR,
        QtMsgType.QtFatalMsg: logging.CRITICAL,
    }

    def handler(mode, context, message):  # noqa: ANN001 - Qt signature
        try:
            logger.log(
                levels.get(mode, logging.INFO),
                "Qt: %s (%s:%s)",
                message,
                context.file or "?",
                context.line or 0,
            )
        except Exception:  # pragma: no cover - never break logging
            pass

    qInstallMessageHandler(handler)
    _qt_handler_installed = True


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _tag(handler: logging.Handler) -> None:
    handler._bookbridge_handler = True  # type: ignore[attr-defined]


def _remove_our_handlers() -> None:
    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, "_bookbridge_handler", False):
            root.removeHandler(handler)
            try:
                handler.close()
            except Exception:
                pass
