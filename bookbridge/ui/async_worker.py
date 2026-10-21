"""Asyncio Worker bridge for PySide6."""

import asyncio
import logging
from typing import Any, Callable, Coroutine, Optional

from PySide6.QtCore import QObject, QThread, Signal

from bookbridge.documents.reparse import reparse_books

logger = logging.getLogger(__name__)


class AsyncWorker(QThread):
    """Run an asyncio coroutine on a dedicated thread.

    The worker is kept alive by the object that creates it until
    ``QThread.finished`` fires. Dropping the reference earlier would destroy a
    running QThread and make Qt abort the process.
    """

    progress_signal = Signal(object, object)  # (job, segment)
    finished_signal = Signal(bool, str)       # (success, message)
    log_signal = Signal(str)                  # (log_line)

    def __init__(
        self,
        coro_func: Callable[[], Coroutine[Any, Any, Any]],
        job_id: Optional[str] = None,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self._coro_func = coro_func
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self.job_id = job_id

    def run(self) -> None:
        label = f"job {self.job_id}" if self.job_id else "background task"
        logger.info("Worker started for %s.", label)
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            res = self._loop.run_until_complete(self._coro_func())
            if isinstance(res, bool):
                message = "Job completed successfully." if res else "Job stopped before completion."
                self.finished_signal.emit(res, message)
            else:
                self.finished_signal.emit(True, "Job completed successfully.")
        except Exception as ex:
            logger.exception("Worker crashed while running %s.", label)
            self.finished_signal.emit(False, f"{type(ex).__name__}: {ex}")
        finally:
            try:
                self._loop.run_until_complete(self._loop.shutdown_asyncgens())
            except Exception:
                logger.debug("Ignoring error while shutting down asyncio generators.", exc_info=True)
            try:
                self._loop.close()
            except Exception:
                logger.debug("Ignoring error while closing asyncio loop.", exc_info=True)
            logger.info("Worker finished for %s.", label)


class BookReparseWorker(QThread):
    completed = Signal(str)

    def __init__(
        self,
        book_ids: list[str],
        epub_granularity: str,
        pdf_granularity: str,
    ):
        super().__init__()
        self.book_ids = book_ids
        self.epub_granularity = epub_granularity
        self.pdf_granularity = pdf_granularity
        self._cancelled = False

    def cancel(self) -> None:
        """Ask the worker to stop before processing the next book."""
        self._cancelled = True

    def run(self) -> None:
        try:
            logger.info(
                "Re-parsing %d existing book(s) (EPUB=%s, PDF=%s).",
                len(self.book_ids),
                self.epub_granularity,
                self.pdf_granularity,
            )
            updated_count, errors = reparse_books(
                self.book_ids,
                self.epub_granularity,
                self.pdf_granularity,
                should_stop=lambda: self._cancelled,
            )
            message = f"Updated blocks for {updated_count} existing book(s)."
            if errors:
                message += " Could not update: " + "; ".join(errors)
            self.completed.emit(message)
        except Exception as exc:
            logger.exception("Background book reparse failed")
            self.completed.emit(f"Could not update existing books: {exc}")
