"""Qt WebChannel bridge between the HTML UI and BookBridge services."""

import itertools
import json
import logging
import uuid
from pathlib import Path
from typing import Any, List, Optional

from PySide6.QtCore import QObject, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog, QMessageBox, QWidget

from bookbridge.config.constants import JobStatus, ProviderType, TranslationStyleType
from bookbridge.config.settings import settings
from bookbridge.logging_setup import get_error_log_path, get_log_path
from bookbridge.database.repositories.book_repo import BookRepository
from bookbridge.database.repositories.credential_repo import CredentialRepository
from bookbridge.database.repositories.glossary_repo import GlossaryRepository
from bookbridge.database.repositories.job_repo import JobRepository
from bookbridge.documents.epub.parser import EpubParser
from bookbridge.documents.pdf.parser import PdfParser
from bookbridge.engine.job_runner import JobRunner
from bookbridge.models.job import TranslationJob
from bookbridge.models.glossary import GlossaryProfile, GlossaryTerm
from bookbridge.config.constants import GlossaryCategory, MatchType
from bookbridge.models.provider import ProviderCredentialMetadata
from bookbridge.models.provider_config import ProviderConfig
from bookbridge.security.keyring_manager import keyring_manager
from bookbridge.ui.async_worker import AsyncWorker, BookReparseWorker

logger = logging.getLogger(__name__)

_LEVEL_ORDER = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


def _tail_lines(path: Path, max_lines: int, level: str = "") -> List[str]:
    """Read log lines, optionally filtered by minimum level.

    Continuation lines (tracebacks, wrapped messages) do not carry a
    ``time | LEVEL | logger`` prefix. They must stay attached to the formatted
    line they belong to, otherwise the default INFO view silently hides every
    traceback. Rotated logs are capped at a few megabytes, so reading the whole
    current file is cheap and also avoids missing an older error.
    """
    if not path.is_file():
        return []
    max_lines = max(1, min(max_lines, 5000))
    threshold = None
    if level:
        try:
            threshold = _LEVEL_ORDER.index(level.strip().upper())
        except ValueError:
            threshold = None

    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        logger.exception("Could not read log file %s", path)
        return []

    if threshold is None:
        return lines[-max_lines:]

    filtered: List[str] = []
    keep_continuations = False
    for line in lines:
        parts = line.split(" | ", 3)
        if len(parts) >= 2 and parts[1].strip() in _LEVEL_ORDER:
            keep_continuations = _LEVEL_ORDER.index(parts[1].strip()) >= threshold
            if keep_continuations:
                filtered.append(line)
        elif keep_continuations:
            # Traceback/context lines belonging to the last selected entry.
            filtered.append(line)
    return filtered[-max_lines:]


class WebBridge(QObject):
    """Expose backend operations as JSON-based WebChannel methods."""

    data_changed = Signal(str)
    job_progress = Signal(str)
    job_finished = Signal(bool, str)
    book_reparse_finished = Signal(str)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.book_repo = BookRepository()
        self.job_repo = JobRepository()
        self.cred_repo = CredentialRepository()
        self.glossary_repo = GlossaryRepository()
        try:
            recovered = self.job_repo.recover_orphaned_jobs()
            if recovered:
                logger.warning(
                    "Marked %d interrupted translation job(s) as paused for resume.",
                    recovered,
                )
        except Exception:
            logger.exception("Could not recover interrupted translation jobs.")
        self.job_runner = JobRunner(self.job_repo, self.book_repo, self.glossary_repo)
        self.worker: Optional[AsyncWorker] = None
        self.reparse_worker: Optional[BookReparseWorker] = None
        self._job_id: Optional[str] = None
        self._progress_seq = itertools.count(1)
        self.job_runner.set_progress_callback(self._on_job_progress)

    def _parent_widget(self) -> Optional[QWidget]:
        parent = self.parent()
        return parent if isinstance(parent, QWidget) else None

    @staticmethod
    def _dump(value: Any) -> str:
        if hasattr(value, "model_dump"):
            value = value.model_dump(mode="json")
        return json.dumps(value, ensure_ascii=False, default=str)

    def _book_summary_dict(self, book: Any) -> dict:
        """Lightweight book entry for the library list.

        Chapters/blocks are fetched on demand through ``get_book_details`` so a
        refresh does not deserialize every book in the library.
        """
        return {
            "id": book.id,
            "title": book.metadata.title,
            "author": book.metadata.author,
            "format": book.source_format.upper(),
            "chapters": [],
        }

    def _book_dict(self, book: Any) -> dict:
        return {
            "id": book.id,
            "title": book.metadata.title,
            "author": book.metadata.author,
            "format": book.source_format.upper(),
            "chapters": [
                {
                    "id": chapter.id,
                    "title": chapter.title,
                    "blocks": [
                        {
                            "type": block.type.value,
                            "text": block.translated_text or block.source_text,
                            "source": block.source_text,
                        }
                        for block in chapter.blocks
                    ],
                }
                for chapter in book.chapters
            ],
        }

    def _job_dict(self, job: Any, provider: str = "", model: str = "") -> dict:
        return {
            "id": job.id,
            "bookId": job.book_id,
            "bookTitle": job.book_title,
            "status": job.status.value.upper(),
            "progress": job.progress_percent,
            "segments": job.completed_segments,
            "segmentsTotal": job.total_segments,
            "cached": job.cached_segments,
            "tokens": job.total_tokens_used,
            "failures": job.failed_segments,
            "retries": job.retried_segments,
            "provider": provider,
            "model": model,
            "chapter": job.current_chapter_title or "",
            "error": job.error_message or "",
            "updatedAt": str(job.updated_at),
        }

    @Slot(result=str)
    def get_state(self) -> str:
        jobs = self.job_repo.list_jobs(limit=50)
        job_media = self.job_repo.get_provider_models([job.id for job in jobs])
        credentials = self.cred_repo.list_credentials()
        profiles = self.glossary_repo.list_profiles()
        books = [
            self._book_summary_dict(book)
            for book in self.book_repo.list_books()
        ]
        return self._dump({
            "books": books,
            "jobs": [
                self._job_dict(job, *job_media.get(job.id, ("", "")))
                for job in jobs
            ],
            "credentials": [
                {
                    "id": cred.id,
                    "provider": cred.extra_config.get("provider_id", cred.provider.value),
                    "name": cred.name,
                    "model": cred.model,
                    "enabled": cred.enabled,
                    "state": cred.state.value.upper(),
                    "tokens": cred.total_tokens_used,
                    "success": cred.success_count,
                    "failures": cred.failure_count,
                    "rpm": cred.effective_rpm,
                    "tpm": cred.effective_tpm,
                    "rpd": cred.effective_rpd,
                }
                for cred in credentials
            ],
            "profiles": [
                {
                    "id": profile.id,
                    "name": profile.name,
                    "genre": profile.genre,
                    "terms": [
                        {
                            "id": term.id,
                            "src": term.source,
                            "ar": term.target,
                            "cat": term.category.value,
                            "pri": term.priority,
                            "type": term.match_type.value,
                            "cs": term.case_sensitive,
                            "locked": term.locked,
                        }
                        for term in profile.terms
                    ],
                }
                for profile in profiles
            ],
            "settings": {
                "dir": str(settings.exports_dir),
                "chunk": settings.max_segment_chars,
                "ctx": settings.context_window_blocks,
                "epub_granularity": settings.epub_block_granularity,
                "pdf_granularity": settings.pdf_block_granularity,
                "retry": settings.max_validation_retries,
                "cool": settings.normal_request_cooldown_seconds,
                "providers": settings.provider_configs,
                "log_dir": str(get_log_path().parent),
                "log_path": str(get_log_path()),
                "error_log_path": str(get_error_log_path()),
            },
        })

    @Slot(str, result=str)
    def get_book_details(self, book_id: str) -> str:
        """Return chapters/blocks for one book, loaded only when inspected."""
        book_id = (book_id or "").strip()
        if not book_id:
            return self._dump({"ok": False, "error": "No book selected."})
        try:
            book = self.book_repo.get_book(book_id)
            if book is None:
                return self._dump({"ok": False, "error": "Book not found."})
            return self._dump({"ok": True, "book": self._book_dict(book)})
        except Exception as exc:
            logger.exception("Could not load details for book %s", book_id)
            return self._dump({"ok": False, "error": f"Could not load the book: {exc}"})

    @Slot(str, str, str, str, result=str)
    def save_provider(self, provider_id: str, name: str, base_url: str, protocol: str) -> str:
        try:
            config = ProviderConfig(id=provider_id.strip() or str(uuid.uuid4()), name=name.strip(), base_url=base_url.strip(), protocol=protocol)
            if not config.name or not config.base_url:
                return self._dump({"ok": False, "error": "Provider name and base URL are required."})
            rows = [row for row in settings.provider_configs if row.get("id") != config.id]
            rows.append(config.model_dump(mode="json"))
            settings.provider_configs = rows
            settings.save()
            self.data_changed.emit("credentials")
            return self._dump({"ok": True, "provider": config.model_dump(mode="json")})
        except (OSError, TypeError, ValueError) as exc:
            return self._dump({"ok": False, "error": str(exc)})

    @Slot(str, str, result=str)
    def delete_provider(self, provider_id: str, replacement: str = "") -> str:
        if any(c.extra_config.get("provider_id") == provider_id for c in self.cred_repo.list_credentials()):
            return self._dump({"ok": False, "error": "Delete or move this provider's API keys first."})
        settings.provider_configs = [row for row in settings.provider_configs if row.get("id") != provider_id]
        settings.save()
        self.data_changed.emit("credentials")
        return self._dump({"ok": True})

    @Slot(str, str, result=str)
    def save_provider_model(self, provider_id: str, model: str) -> str:
        model = model.strip()
        for row in settings.provider_configs:
            if row.get("id") == provider_id:
                if model and model not in row.setdefault("models", []):
                    row["models"].append(model)
                settings.save()
                self.data_changed.emit("credentials")
                return self._dump({"ok": True})
        return self._dump({"ok": False, "error": "Provider not found."})

    @Slot(str, str, result=str)
    def delete_provider_model(self, provider_id: str, model: str) -> str:
        for row in settings.provider_configs:
            if row.get("id") == provider_id:
                row["models"] = [item for item in row.get("models", []) if item != model]
                settings.save()
                self.data_changed.emit("credentials")
                return self._dump({"ok": True})
        return self._dump({"ok": False, "error": "Provider not found."})

    @Slot(str, result=str)
    def import_book(self, file_format: str) -> str:
        extension = file_format.lower().lstrip(".")
        filters = "EPUB Files (*.epub)" if extension == "epub" else "PDF Files (*.pdf)"
        file_path, _ = QFileDialog.getOpenFileName(
            self._parent_widget(),
            f"Import {extension.upper()} File",
            "",
            filters,
        )
        if not file_path:
            return self._dump({"cancelled": True})
        try:
            parser = EpubParser() if extension == "epub" else PdfParser()
            logger.info("Importing %s book: %s", extension.upper(), file_path)
            book = parser.parse(Path(file_path))
            self.book_repo.save_book(book)
            logger.info(
                "Imported %s (%d chapters) from %s",
                book.metadata.title,
                len(book.chapters),
                file_path,
            )
            self.data_changed.emit("books")
            return self._dump({"ok": True, "book": self._book_dict(book)})
        except Exception as exc:
            logger.exception("Book import failed for %s", file_path)
            return self._dump({"ok": False, "error": str(exc)})

    @Slot(result=str)
    def browse_directory(self) -> str:
        current_dir = str(settings.exports_dir) if settings.exports_dir.exists() else ""
        dir_path = QFileDialog.getExistingDirectory(
            self._parent_widget(),
            "Select Export Directory",
            current_dir,
        )
        return self._dump({"path": dir_path or ""})

    @Slot(str, result=str)
    def delete_book(self, book_id: str) -> str:
        self.book_repo.delete_book(book_id)
        self.data_changed.emit("books")
        return self._dump({"ok": True})

    @Slot(str, str, str, str, str, str, result=str)
    def create_job(
        self,
        book_id: str,
        output_format: str,
        style: str,
        glossary_id: str = "",
        strategy: str = "auto",
        model: str = "",
    ) -> str:
        """Create a translation job and run it on a background thread."""
        book_id = (book_id or "").strip()
        logger.info(
            "Translation requested: book=%r format=%r style=%r glossary=%r strategy=%r model=%r",
            book_id,
            output_format,
            style,
            glossary_id,
            strategy,
            model,
        )
        if self.worker is not None:
            if self.worker.isRunning():
                message = "A translation job is already running. Wait for it to finish or cancel it first."
            else:
                message = "The previous translation is still shutting down. Try again in a moment."
            logger.warning("Rejected new job: %s", message)
            return self._dump({"ok": False, "error": message})
        if not book_id:
            return self._dump({"ok": False, "error": "No book selected."})
        try:
            book = self.book_repo.get_book(book_id)
            if not book:
                logger.warning("Rejected new job: book %s not found.", book_id)
                return self._dump({"ok": False, "error": "Book not found. Re-import it and try again."})
            if not self.cred_repo.list_credentials(only_enabled=True):
                message = (
                    "No API credentials are configured. Add an API key under "
                    "API Credentials before starting a translation."
                )
                logger.warning("Rejected new job: no enabled credentials.")
                return self._dump({"ok": False, "error": message})

            style_values = {
                "Literary — Flowing Prose": TranslationStyleType.LITERARY,
                "Faithful — Close to Source": TranslationStyleType.LITERAL,
                "Xianxia — Genre Native": TranslationStyleType.WEB_NOVEL,
                "Fast Draft — Speed First": TranslationStyleType.NATURAL,
            }
            custom_settings = {}
            if strategy and strategy.strip():
                custom_settings["strategy"] = strategy.strip()
            if model and model.strip() and model != "No models configured":
                custom_settings["preferred_model"] = model.strip()

            job = TranslationJob(
                book_id=book.id,
                book_title=book.metadata.title,
                output_format=output_format.lower(),
                style=style_values.get(style, TranslationStyleType.NATURAL),
                glossary_profile_id=glossary_id.strip() if glossary_id and glossary_id.strip() else None,
                custom_settings=custom_settings,
            )
            self.job_repo.create_job(job)
            self._job_id = job.id
            logger.info("Created job %s for '%s'.", job.id, book.metadata.title)
            self._start_job_worker(job)
            return self._dump({"ok": True, "job": self._job_dict(job)})
        except Exception as exc:
            logger.exception("Could not start translation job for book %s", book_id)
            return self._dump({"ok": False, "error": f"Could not start the translation: {exc}"})

    def _start_job_worker(self, job: TranslationJob) -> None:
        """Start a worker for a new or resumable job."""
        # Reset control flags synchronously, before the thread starts. Doing it
        # inside the worker would discard a Cancel click made in the QUEUED
        # window between create_job() and the worker's first instruction.
        self.job_runner.reset_control()

        # Keep a strong reference until QThread.finished fires. Dropping the
        # only reference from inside finished_signal (which is emitted while
        # the thread is still running) makes Qt abort the whole process.
        worker = AsyncWorker(lambda: self.job_runner.run_job(job.id), job_id=job.id)
        # Connect through plain callables instead of bound methods of this
        # WebChannel object. Connecting a cross-thread signal to a bound
        # method can break Qt WebChannel's own signal forwarding, after
        # which the UI silently stops receiving progress updates.
        worker.progress_signal.connect(
            lambda job_state, segment: self._on_worker_progress(job_state, segment)
        )
        # Capture the job id: using the mutable self._job_id later could
        # announce the wrong job if another job starts during thread teardown.
        worker.finished_signal.connect(
            lambda success, message, job_id=job.id: self._on_worker_finished(
                job_id, success, message
            )
        )
        worker.finished.connect(lambda worker=worker: self._release_worker(worker))
        self.worker = worker
        try:
            worker.start()
        except Exception:
            self.worker = None
            worker.deleteLater()
            raise
        logger.info("Worker thread started for job %s.", job.id)
        self._dispatch_progress(job, None)

    @Slot(str, result=str)
    def resume_job(self, book_id: str) -> str:
        """Resume a paused job, or restart an unfinished job after a restart."""
        book_id = (book_id or "").strip()
        if not book_id:
            return self._dump({"ok": False, "error": "No book selected."})
        try:
            if self.worker is not None:
                if not self.worker.isRunning():
                    return self._dump({
                        "ok": False,
                        "error": "The previous translation is still shutting down. Try again in a moment.",
                    })
                job = self.job_repo.get_job(self._job_id) if self._job_id else None
                if job is None or job.book_id != book_id or job.status != JobStatus.PAUSED:
                    return self._dump({
                        "ok": False,
                        "error": "A different translation job is already running.",
                    })
                self.job_runner.resume()
                job.status = JobStatus.RUNNING
                media = self.job_repo.get_provider_models([job.id]).get(job.id, ("", ""))
                logger.info("Resumed paused job %s.", job.id)
                return self._dump({
                    "ok": True,
                    "resumed": True,
                    "job": self._job_dict(job, *media),
                })

            job = self.job_repo.get_latest_resumable_job_for_book(book_id)
            if job is None:
                return self._dump({"ok": False, "error": "No translation job was found for this book."})
            resumable = {
                JobStatus.PAUSED,
                JobStatus.CANCELLED,
                JobStatus.NEEDS_REVIEW,
                JobStatus.FAILED,
            }
            if job.status not in resumable:
                return self._dump({
                    "ok": False,
                    "error": "This job is already complete. Start a new translation instead.",
                })
            if not self.cred_repo.list_credentials(only_enabled=True):
                return self._dump({
                    "ok": False,
                    "error": (
                        "No API credentials are configured. Add an API key under "
                        "API Credentials before resuming."
                    ),
                })
            self._job_id = job.id
            # Show RUNNING immediately; the worker will persist the same status
            # once it has reloaded the book and segmented state.
            job.status = JobStatus.RUNNING
            media = self.job_repo.get_provider_models([job.id]).get(job.id, ("", ""))
            self._start_job_worker(job)
            logger.info("Resumed unfinished job %s for book %s.", job.id, book_id)
            return self._dump({
                "ok": True,
                "resumed": True,
                "job": self._job_dict(job, *media),
            })
        except Exception as exc:
            logger.exception("Could not resume translation for book %s", book_id)
            return self._dump({"ok": False, "error": f"Could not resume the translation: {exc}"})

    @Slot(str, str, str, str, result=str)
    def save_credential(self, provider: str, name: str, model: str, secret: str) -> str:
        try:
            provider_config = next((row for row in settings.provider_configs if row.get("id") == provider), None)
            provider_type = ProviderType.CUSTOM if provider_config else ProviderType(provider)
            credential = ProviderCredentialMetadata(
                provider=provider_type,
                name=name.strip(),
                model=model.strip(),
                rate_limit_rpm=provider_config.get("rate_limit_rpm") if provider_config else None,
                rate_limit_tpm=provider_config.get("rate_limit_tpm") if provider_config else None,
                rate_limit_rpd=provider_config.get("rate_limit_rpd") if provider_config else None,
                extra_config={"provider_id": provider} if provider_config else {},
            )
            if not credential.name or not credential.model or not secret.strip():
                return self._dump({"ok": False, "error": "Provider, name, model, and secret are required."})
            if not keyring_manager.save_secret(credential.id, secret.strip()):
                return self._dump({"ok": False, "error": "The credential could not be saved securely."})
            self.cred_repo.save_credential_metadata(credential)
            self.data_changed.emit("credentials")
            return self._dump({"ok": True})
        except (TypeError, ValueError) as exc:
            return self._dump({"ok": False, "error": str(exc)})

    @Slot(str, str, str, str, result=str)
    def update_credential(self, credential_id: str, name: str, model: str, secret: str = "") -> str:
        credential = self.cred_repo.get_credential(credential_id)
        if not credential or not name.strip() or not model.strip():
            return self._dump({"ok": False, "error": "Credential, name, and model are required."})
        credential.name = name.strip()
        credential.model = model.strip()
        if secret and secret.strip():
            if not keyring_manager.save_secret(credential.id, secret.strip()):
                return self._dump({"ok": False, "error": "The new API secret could not be saved securely."})
        self.cred_repo.save_credential_metadata(credential)
        self.data_changed.emit("credentials")
        return self._dump({"ok": True})

    @Slot(str, result=str)
    def delete_credential(self, credential_id: str) -> str:
        self.cred_repo.delete_credential(credential_id)
        keyring_manager.delete_secret(credential_id)
        self.data_changed.emit("credentials")
        return self._dump({"ok": True})

    @Slot(str, str, result=str)
    def create_glossary_profile(self, name: str, genre: str) -> str:
        if not name.strip():
            return self._dump({"ok": False, "error": "Profile name is required."})
        profile = GlossaryProfile(name=name.strip(), genre=genre.strip() or "General")
        self.glossary_repo.save_profile(profile)
        self.data_changed.emit("glossary")
        return self._dump({"ok": True, "profileId": profile.id})

    @Slot(str, str, str, int, str, bool, bool, result=str)
    def create_glossary_term(
        self,
        profile_id: str,
        source: str,
        target: str,
        priority: int,
        category: str,
        case_sensitive: bool,
        locked: bool,
    ) -> str:
        if not source.strip() or not target.strip():
            return self._dump({"ok": False, "error": "Source and target terms are required."})
        profile = self.glossary_repo.get_profile(profile_id)
        if not profile:
            return self._dump({"ok": False, "error": "Glossary profile not found."})
        try:
            term = GlossaryTerm(
                glossary_id=profile.id,
                source=source.strip(),
                target=target.strip(),
                priority=max(1, min(1000, priority)),
                category=GlossaryCategory(category),
                match_type=MatchType.PHRASE,
                case_sensitive=case_sensitive,
                locked=locked,
            )
        except ValueError as exc:
            return self._dump({"ok": False, "error": str(exc)})
        profile.terms.append(term)
        self.glossary_repo.save_profile(profile)
        self.data_changed.emit("glossary")
        return self._dump({"ok": True, "termId": term.id})

    @Slot(result=str)
    def pause_job(self) -> str:
        logger.info("Pause requested for job %s.", self._job_id)
        self.job_runner.pause()
        return self._dump({"ok": True})

    @Slot(str, result=str)
    def cancel_job(self, book_id: str = "") -> str:
        logger.info("Cancel requested for job %s.", self._job_id or book_id or "?")
        if self.worker is not None:
            # The running worker owns the job state and will persist CANCELLED
            # at the next segment boundary.
            self.job_runner.cancel()
            return self._dump({"ok": True, "active": True})

        book_id = (book_id or "").strip()
        job = None
        if book_id:
            job = self.job_repo.get_latest_resumable_job_for_book(book_id)
        elif self._job_id:
            job = self.job_repo.get_job(self._job_id)
            if job is not None and job.status not in (
                JobStatus.PAUSED,
                JobStatus.QUEUED,
                JobStatus.RUNNING,
                JobStatus.CANCELLED,
                JobStatus.NEEDS_REVIEW,
                JobStatus.FAILED,
            ):
                job = None
        if job is None:
            return self._dump({"ok": False, "error": "No paused translation job was found."})
        if job.status in (
            JobStatus.PAUSED,
            JobStatus.QUEUED,
            JobStatus.RUNNING,
            JobStatus.NEEDS_REVIEW,
            JobStatus.FAILED,
        ):
            # A paused job restored after a restart has no worker to receive
            # the cancel flag. Persist the state change directly.
            self.job_repo.clear_job_error(job.id)
            self.job_repo.update_job_status(job.id, JobStatus.CANCELLED)
            job.status = JobStatus.CANCELLED
            job.error_message = None
            self._dispatch_progress(job, None)
            logger.info("Marked paused job %s as cancelled.", job.id)
        return self._dump({"ok": True, "job": self._job_dict(job)})

    @Slot(int, str, result=str)
    def read_logs(self, max_lines: int = 400, level: str = "") -> str:
        """Return the newest log lines for the Diagnostics page."""
        try:
            path = get_log_path()
            lines = _tail_lines(path, max_lines, level)
            return self._dump({
                "ok": True,
                "path": str(path),
                "errorPath": str(get_error_log_path()),
                "lines": lines,
            })
        except OSError as exc:
            logger.exception("Could not read application log")
            return self._dump({"ok": False, "error": str(exc), "lines": []})

    @Slot(result=str)
    def open_logs_folder(self) -> str:
        """Open the folder that contains the log files."""
        path = get_log_path()
        folder = path.parent
        try:
            folder.mkdir(parents=True, exist_ok=True)
            opened = QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
            logger.info("Opened log folder %s (success=%s).", folder, opened)
            return self._dump({"ok": bool(opened), "path": str(folder)})
        except OSError as exc:
            logger.exception("Could not open log folder %s", folder)
            return self._dump({"ok": False, "error": str(exc), "path": str(folder)})

    @Slot(str, str, result=str)
    def log_client(self, level: str, message: str) -> str:
        """Persist a message from the HTML/JavaScript layer."""
        levels = {
            "debug": logging.DEBUG,
            "info": logging.INFO,
            "warning": logging.WARNING,
            "warn": logging.WARNING,
            "error": logging.ERROR,
            "critical": logging.CRITICAL,
        }
        text = (message or "").strip()
        if len(text) > 12000:
            text = text[:12000] + " …(truncated)"
        logging.getLogger("bookbridge.ui.js").log(
            levels.get((level or "").lower(), logging.INFO), "%s", text
        )
        return self._dump({"ok": True})

    @Slot(str, int, int, int, float, str, str, result=str)
    def save_settings(
        self,
        directory: str,
        chunk: int,
        context: int,
        retries: int,
        cooldown: float,
        epub_granularity: str,
        pdf_granularity: str,
    ) -> str:
        if epub_granularity not in ("paragraph", "chapter"):
            return self._dump({"ok": False, "error": "Invalid EPUB block granularity."})
        if pdf_granularity not in ("paragraph", "page"):
            return self._dump({"ok": False, "error": "Invalid PDF block granularity."})

        epub_changed = epub_granularity != settings.epub_block_granularity
        pdf_changed = pdf_granularity != settings.pdf_block_granularity
        if (epub_changed or pdf_changed) and self.worker is not None:
            return self._dump({
                "ok": False,
                "error": "Wait for the active translation to finish before changing block granularity.",
            })
        if self.reparse_worker is not None:
            return self._dump({
                "ok": False,
                "error": "Existing books are still being updated. Please try again when that finishes.",
            })

        original_settings = {
            "export_directory": settings.export_directory,
            "max_segment_chars": settings.max_segment_chars,
            "context_window_blocks": settings.context_window_blocks,
            "max_validation_retries": settings.max_validation_retries,
            "normal_request_cooldown_seconds": settings.normal_request_cooldown_seconds,
            "epub_block_granularity": settings.epub_block_granularity,
            "pdf_block_granularity": settings.pdf_block_granularity,
        }
        try:
            changed_formats = set()
            if epub_changed:
                changed_formats.add("epub")
            if pdf_changed:
                changed_formats.add("pdf")
            book_ids = [
                book.id
                for book in self.book_repo.list_books()
                if book.source_format in changed_formats
            ]

            settings.export_directory = Path(directory.strip()) if directory.strip() else None
            settings.max_segment_chars = max(200, min(5000, chunk))
            settings.context_window_blocks = max(0, min(10, context))
            settings.max_validation_retries = max(0, min(5, retries))
            settings.normal_request_cooldown_seconds = max(0.0, min(60.0, cooldown))
            settings.epub_block_granularity = epub_granularity
            settings.pdf_block_granularity = pdf_granularity
            settings.ensure_directories()
            settings.save()
            self.data_changed.emit("settings")
            if book_ids:
                worker = BookReparseWorker(
                    book_ids,
                    epub_granularity,
                    pdf_granularity,
                )
                # Relaying through lambdas is required: connecting a
                # cross-thread signal directly to a bound method of the
                # registered WebChannel object silently disables all signal
                # forwarding to JavaScript.
                worker.completed.connect(
                    lambda message: self._on_book_reparse_finished(message)
                )
                worker.finished.connect(
                    lambda worker=worker: self._release_reparse_worker(worker)
                )
                self.reparse_worker = worker
                try:
                    worker.start()
                except Exception:
                    self.reparse_worker = None
                    worker.deleteLater()
                    raise
            return self._dump({"ok": True, "reparsing": len(book_ids)})
        except (OSError, TypeError, ValueError) as exc:
            for field_name, value in original_settings.items():
                setattr(settings, field_name, value)
            return self._dump({"ok": False, "error": str(exc)})

    def _on_book_reparse_finished(self, message: str) -> None:
        self.book_reparse_finished.emit(message)
        self.data_changed.emit("books")

    def _release_reparse_worker(self, worker: BookReparseWorker) -> None:
        if self.reparse_worker is worker:
            self.reparse_worker = None
        try:
            worker.deleteLater()
        except RuntimeError:
            pass

    def running_worker_labels(self) -> List[str]:
        """Names of background threads that are still alive or about to run."""
        labels = []
        # A worker reference appears before QThread.isRunning() flips to True.
        # Treat both as busy so closing cannot race the worker's start-up.
        if self.worker is not None:
            labels.append("translation")
        if self.reparse_worker is not None:
            labels.append("book update")
        return labels

    def request_shutdown(self) -> None:
        """Ask all background workers to stop without destroying QThreads."""
        if self.worker is not None:
            logger.info("Shutdown requested: cancelling the translation job.")
            self.job_runner.cancel()
        if self.reparse_worker is not None:
            logger.info("Shutdown requested: cancelling the book reparse.")
            self.reparse_worker.cancel()

    def _on_job_progress(self, job: Any, segment: Any) -> None:
        """Route progress to the UI. Always go through the worker signal when one is
        active so Qt's cross-thread marshalling guarantees delivery on the GUI thread."""
        if self.worker is not None:
            self.worker.progress_signal.emit(job, segment)
        else:
            self._dispatch_progress(job, segment)

    def _on_worker_progress(self, job: Any, segment: Any) -> None:
        self._dispatch_progress(job, segment)

    def _dispatch_progress(self, job: Any, segment: Any) -> None:
        self.job_progress.emit(self._dump({
            "seq": next(self._progress_seq),
            "job": self._job_dict(
                job,
                getattr(segment, "provider_used", "") or "" if segment else "",
                getattr(segment, "model_used", "") or "" if segment else "",
            ),
            "segment": {
                "source": segment.source_text,
                "translated": segment.translated_text or "",
                "provider": segment.provider_used or "",
                "model": segment.model_used or "",
            } if segment else None,
        }))

    def _on_worker_finished(self, job_id: str, success: bool, message: str) -> None:
        """Handle the worker's custom finished signal.

        Do **not** drop ``self.worker`` here: this signal is emitted from inside
        ``QThread.run()``. Releasing the last reference at that point destroys
        the QThread while it is still running and Qt aborts the process. The
        reference is released from ``QThread.finished`` via ``_release_worker``.
        """
        job = None
        if job_id:
            try:
                job = self.job_repo.get_job(job_id)
            except Exception:
                logger.exception("Could not reload job %s after it finished.", job_id)
        if job is not None and job.status == JobStatus.CANCELLED and not success:
            message = "Translation cancelled. Progress is saved."
        elif not success and job is not None and job.error_message:
            message = job.error_message
        elif success and (not message or message == "Job completed successfully."):
            message = "Translation completed successfully."
        if job is not None:
            logger.info(
                "Job %s finished: success=%s status=%s segments=%d/%d failures=%d message=%s",
                job.id,
                success,
                job.status.value,
                job.completed_segments,
                job.total_segments,
                job.failed_segments,
                message,
            )
        else:
            logger.info("Job finished: success=%s message=%s", success, message)
        self.job_finished.emit(success, message)
        self.data_changed.emit("jobs")

    def _release_worker(self, worker: AsyncWorker) -> None:
        """Release a QThread only after Qt reports it has really finished."""
        try:
            worker.wait(5000)
        except RuntimeError:
            pass
        if self.worker is worker:
            self.worker = None
        try:
            worker.deleteLater()
        except RuntimeError:
            pass
        logger.debug("Worker thread released for job %s.", getattr(worker, "job_id", None))
