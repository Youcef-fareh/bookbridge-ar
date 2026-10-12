"""Qt WebChannel bridge between the HTML UI and BookBridge services."""

import json
import uuid
from pathlib import Path
from typing import Any, Optional

from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtWidgets import QFileDialog, QMessageBox, QWidget

from bookbridge.config.constants import JobStatus, ProviderType, TranslationStyleType
from bookbridge.config.settings import settings
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
from bookbridge.ui.async_worker import AsyncWorker


class WebBridge(QObject):
    """Expose backend operations as JSON-based WebChannel methods."""

    data_changed = Signal(str)
    job_progress = Signal(str)
    job_finished = Signal(bool, str)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.book_repo = BookRepository()
        self.job_repo = JobRepository()
        self.cred_repo = CredentialRepository()
        self.glossary_repo = GlossaryRepository()
        self.job_runner = JobRunner(self.job_repo, self.book_repo, self.glossary_repo)
        self.worker: Optional[AsyncWorker] = None
        self._job_id: Optional[str] = None
        self.job_runner.set_progress_callback(self._on_job_progress)

    def _parent_widget(self) -> Optional[QWidget]:
        parent = self.parent()
        return parent if isinstance(parent, QWidget) else None

    @staticmethod
    def _dump(value: Any) -> str:
        if hasattr(value, "model_dump"):
            value = value.model_dump(mode="json")
        return json.dumps(value, ensure_ascii=False, default=str)

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

    def _job_dict(self, job: Any) -> dict:
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
            "provider": "",
            "model": "",
            "updatedAt": str(job.updated_at),
        }

    @Slot(result=str)
    def get_state(self) -> str:
        books = self.book_repo.list_books()
        jobs = self.job_repo.list_jobs(limit=50)
        credentials = self.cred_repo.list_credentials()
        profiles = self.glossary_repo.list_profiles()
        return self._dump({
            "books": [self._book_dict(self.book_repo.get_book(b.id)) for b in books],
            "jobs": [self._job_dict(job) for job in jobs],
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
                "retry": settings.max_validation_retries,
                "cool": settings.normal_request_cooldown_seconds,
                "providers": settings.provider_configs,
            },
        })

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
            book = parser.parse(Path(file_path))
            self.book_repo.save_book(book)
            self.data_changed.emit("books")
            return self._dump({"ok": True, "book": self._book_dict(book)})
        except Exception as exc:
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

    @Slot(str, str, str, result=str)
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
        book = self.book_repo.get_book(book_id)
        if not book:
            return self._dump({"ok": False, "error": "Book not found."})
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
        self.worker = AsyncWorker(lambda: self.job_runner.run_job(job.id))
        self.worker.progress_signal.connect(self._on_worker_progress)
        self.worker.finished_signal.connect(self._on_worker_finished)
        self.worker.start()
        return self._dump({"ok": True, "job": self._job_dict(job)})

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

    @Slot(str, str, str, result=str)
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
        self.job_runner.pause()
        return self._dump({"ok": True})

    @Slot(result=str)
    def cancel_job(self) -> str:
        self.job_runner.cancel()
        return self._dump({"ok": True})

    @Slot(str, int, int, int, float, result=str)
    def save_settings(self, directory: str, chunk: int, context: int, retries: int, cooldown: float) -> str:
        settings.export_directory = Path(directory.strip()) if directory.strip() else None
        settings.max_segment_chars = max(200, min(5000, chunk))
        settings.context_window_blocks = max(0, min(10, context))
        settings.max_validation_retries = max(0, min(5, retries))
        settings.normal_request_cooldown_seconds = max(0.0, min(60.0, cooldown))
        try:
            settings.save()
            settings.ensure_directories()
            self.data_changed.emit("settings")
            return self._dump({"ok": True})
        except OSError as exc:
            return self._dump({"ok": False, "error": str(exc)})

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
            "job": self._job_dict(job),
            "segment": {
                "source": segment.source_text,
                "translated": segment.translated_text or "",
                "provider": segment.provider_used or "",
                "model": segment.model_used or "",
            } if segment else None,
        }))

    def _on_worker_finished(self, success: bool, message: str) -> None:
        self.worker = None  # Clear reference so future callbacks use direct dispatch
        self.job_finished.emit(success, message)
        self.data_changed.emit("jobs")
