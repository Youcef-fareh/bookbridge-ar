"""Asyncio Worker bridge for PySide6."""

import asyncio
import logging
from typing import Any, Callable, Coroutine
from PySide6.QtCore import QObject, QThread, Signal
from bookbridge.documents.reparse import reparse_books
from bookbridge.models.job import TranslationJob, Segment

logger = logging.getLogger(__name__)


class AsyncWorker(QThread):
    progress_signal = Signal(object, object)  # (job, segment)
    finished_signal = Signal(bool, str)       # (success, message)
    log_signal = Signal(str)                  # (log_line)

    def __init__(self, coro_func: Callable[[], Coroutine[Any, Any, Any]]):
        super().__init__()
        self._coro_func = coro_func
        self._loop: asyncio.AbstractEventLoop = None

    def run(self) -> None:
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
            logger.exception("AsyncWorker encountered error")
            self.finished_signal.emit(False, str(ex))
        finally:
            self._loop.close()


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

    def run(self) -> None:
        try:
            updated_count, errors = reparse_books(
                self.book_ids,
                self.epub_granularity,
                self.pdf_granularity,
            )
            message = f"Updated blocks for {updated_count} existing book(s)."
            if errors:
                message += " Could not update: " + "; ".join(errors)
            self.completed.emit(message)
        except Exception as exc:
            logger.exception("Background book reparse failed")
            self.completed.emit(f"Could not update existing books: {exc}")
