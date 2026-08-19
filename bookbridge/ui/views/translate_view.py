"""Translation Studio & Real-time Progress Monitor View."""

import asyncio
from pathlib import Path
from typing import Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from bookbridge.config.constants import JobStatus, ProviderType, TranslationStyleType
from bookbridge.config.settings import settings
from bookbridge.database.repositories.book_repo import BookRepository
from bookbridge.database.repositories.glossary_repo import GlossaryRepository
from bookbridge.database.repositories.job_repo import JobRepository
from bookbridge.engine.job_runner import JobRunner
from bookbridge.engine.translator import TranslationPipeline
from bookbridge.models.book import Book
from bookbridge.models.glossary import GlossaryProfile
from bookbridge.models.job import TranslationJob, Segment
from bookbridge.models.style import STYLE_PRESETS
from bookbridge.renderers.epub import EpubRenderer
from bookbridge.renderers.pdf import PdfRenderer
from bookbridge.segmentation.engine import SegmentationEngine
from bookbridge.ui.async_worker import AsyncWorker


class PreviewDialog(QDialog):
    def __init__(self, sample_text: str, translated_text: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Sample Translation Preview (معاينة الترجمة)")
        self.resize(750, 500)
        layout = QVBoxLayout(self)

        lbl = QLabel("Review translation quality, glossary terminology, and Arabic formatting:")
        lbl.setStyleSheet("font-weight: 600; color: #f8fafc;")
        layout.addWidget(lbl)

        splitter = QSplitter(Qt.Horizontal)

        # Source text box
        src_box = QFrame()
        src_layout = QVBoxLayout(src_box)
        src_layout.addWidget(QLabel("Source English:"))
        src_edit = QTextEdit()
        src_edit.setStyleSheet(
            "background-color: #1a1e2b; color: #f1f5f9; "
            "selection-background-color: #6366f1;"
        )
        src_edit.setPlainText(sample_text)
        src_edit.setReadOnly(True)
        src_layout.addWidget(src_edit)
        splitter.addWidget(src_box)

        # Translated Arabic text box
        trans_box = QFrame()
        trans_layout = QVBoxLayout(trans_box)
        trans_layout.addWidget(QLabel("Translated Arabic (RTL):"))
        trans_edit = QTextEdit()
        trans_edit.setStyleSheet(
            "background-color: #1a1e2b; color: #f1f5f9; "
            "selection-background-color: #6366f1;"
        )
        trans_edit.setLayoutDirection(Qt.RightToLeft)
        trans_edit.setPlainText(translated_text)
        trans_edit.setReadOnly(True)
        trans_layout.addWidget(trans_edit)
        splitter.addWidget(trans_box)

        layout.addWidget(splitter)

        close_btn = QPushButton("Close Preview")
        close_btn.setProperty("class", "PrimaryBtn")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignRight)


class TranslateView(QWidget):
    job_updated = Signal(object, object)

    def __init__(
        self,
        book_repo: BookRepository,
        job_repo: JobRepository,
        glossary_repo: GlossaryRepository,
    ):
        super().__init__()
        self.book_repo = book_repo
        self.job_repo = job_repo
        self.glossary_repo = glossary_repo
        self.job_runner = JobRunner(job_repo, book_repo, glossary_repo)
        self.epub_renderer = EpubRenderer()
        self.pdf_renderer = PdfRenderer()

        self.current_book: Optional[Book] = None
        self.current_job: Optional[TranslationJob] = None
        self.worker: Optional[AsyncWorker] = None

        self._setup_ui()
        self.job_runner.set_progress_callback(self._on_job_progress)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Title
        title = QLabel("Translation Studio & Monitor")
        title.setStyleSheet("font-size: 22px; font-weight: 800; color: #ffffff;")
        layout.addWidget(title)

        # Configuration Card
        config_card = QFrame()
        config_card.setProperty("class", "Card")
        config_layout = QGridLayout(config_card)
        config_layout.setSpacing(12)

        # Row 0: Book Selector
        book_label = QLabel("Book to Translate:")
        book_label.setStyleSheet("color: #f1f5f9;")
        config_layout.addWidget(book_label, 0, 0)
        self.book_combo = QComboBox()
        self.book_combo.currentIndexChanged.connect(self._on_book_changed)
        config_layout.addWidget(self.book_combo, 0, 1)

        # Row 0: Output Format
        format_label = QLabel("Output Format:")
        format_label.setStyleSheet("color: #f1f5f9;")
        config_layout.addWidget(format_label, 0, 2)
        self.format_combo = QComboBox()
        self.format_combo.addItems(["EPUB", "PDF"])
        config_layout.addWidget(self.format_combo, 0, 3)

        # Row 1: Translation Style
        style_label = QLabel("Translation Style:")
        style_label.setStyleSheet("color: #f1f5f9;")
        config_layout.addWidget(style_label, 1, 0)
        self.style_combo = QComboBox()
        for style_type, cfg in STYLE_PRESETS.items():
            self.style_combo.addItem(cfg.name, style_type.value)
        config_layout.addWidget(self.style_combo, 1, 1)

        # Row 1: Glossary Profile
        glossary_label = QLabel("Glossary Profile:")
        glossary_label.setStyleSheet("color: #f1f5f9;")
        config_layout.addWidget(glossary_label, 1, 2)
        self.glossary_combo = QComboBox()
        config_layout.addWidget(self.glossary_combo, 1, 3)

        # Row 2: Provider Strategy
        provider_label = QLabel("Provider Strategy:")
        provider_label.setStyleSheet("color: #f1f5f9;")
        config_layout.addWidget(provider_label, 2, 0)
        self.provider_combo = QComboBox()
        self.provider_combo.addItem("Auto Failover (All Available Keys)", "auto")
        self.provider_combo.addItem("Prefer Gemini", ProviderType.GEMINI.value)
        self.provider_combo.addItem("Prefer Groq", ProviderType.GROQ.value)
        self.provider_combo.addItem("Prefer TokenRouter", ProviderType.TOKENROUTER.value)
        self.provider_combo.addItem("Prefer OrCarRouter", ProviderType.ORCAROUTER.value)
        config_layout.addWidget(self.provider_combo, 2, 1)

        # Buttons in Config Card
        btn_bar = QHBoxLayout()
        self.preview_btn = QPushButton("Translate Sample (Preview)")
        self.preview_btn.setProperty("class", "SecondaryBtn")
        self.preview_btn.clicked.connect(self._on_preview_sample)
        btn_bar.addWidget(self.preview_btn)

        self.start_btn = QPushButton("Start Full Translation")
        self.start_btn.setProperty("class", "PrimaryBtn")
        self.start_btn.clicked.connect(self._on_start_or_resume)
        btn_bar.addWidget(self.start_btn)

        self.pause_btn = QPushButton("Pause")
        self.pause_btn.setProperty("class", "SecondaryBtn")
        self.pause_btn.setEnabled(False)
        self.pause_btn.clicked.connect(self._on_pause)
        btn_bar.addWidget(self.pause_btn)

        self.export_btn = QPushButton("Export Output Book")
        self.export_btn.setProperty("class", "SuccessBtn")
        self.export_btn.setEnabled(False)
        self.export_btn.clicked.connect(self._on_export_book)
        btn_bar.addWidget(self.export_btn)

        config_layout.addLayout(btn_bar, 3, 0, 1, 4)
        layout.addWidget(config_card)

        # Progress Monitor Card
        monitor_card = QFrame()
        monitor_card.setProperty("class", "Card")
        monitor_layout = QVBoxLayout(monitor_card)

        self.lbl_progress_status = QLabel("Ready to start translation.")
        self.lbl_progress_status.setStyleSheet("font-weight: 700; color: #f8fafc; font-size: 14px;")
        monitor_layout.addWidget(self.lbl_progress_status)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        monitor_layout.addWidget(self.progress_bar)

        # Metric stats row
        stats_layout = QHBoxLayout()
        self.lbl_stat_segments = QLabel("Segments: 0 / 0")
        self.lbl_stat_cached = QLabel("Cached: 0")
        self.lbl_stat_tokens = QLabel("Tokens: 0")
        self.lbl_stat_provider = QLabel("Active Provider: None")

        for lbl in (self.lbl_stat_segments, self.lbl_stat_cached, self.lbl_stat_tokens, self.lbl_stat_provider):
            lbl.setStyleSheet("font-size: 12px; color: #94a3b8; font-weight: 600;")
            stats_layout.addWidget(lbl)
        monitor_layout.addLayout(stats_layout)

        layout.addWidget(monitor_card)

        # Live Segment Stream (Source vs Translation)
        stream_splitter = QSplitter(Qt.Horizontal)

        src_stream_frame = QFrame()
        src_stream_frame.setProperty("class", "Card")
        src_stream_layout = QVBoxLayout(src_stream_frame)
        src_stream_layout.addWidget(QLabel("Live Source Segment (English):"))
        self.src_stream_edit = QPlainTextEdit()
        self.src_stream_edit.setStyleSheet(
            "background-color: #1a1e2b; color: #f1f5f9; "
            "selection-background-color: #6366f1;"
        )
        self.src_stream_edit.setReadOnly(True)
        src_stream_layout.addWidget(self.src_stream_edit)
        stream_splitter.addWidget(src_stream_frame)

        ar_stream_frame = QFrame()
        ar_stream_frame.setProperty("class", "Card")
        ar_stream_layout = QVBoxLayout(ar_stream_frame)
        ar_stream_layout.addWidget(QLabel("Live Translated Output (Arabic RTL):"))
        self.ar_stream_edit = QPlainTextEdit()
        self.ar_stream_edit.setStyleSheet(
            "background-color: #1a1e2b; color: #f1f5f9; "
            "selection-background-color: #6366f1;"
        )
        self.ar_stream_edit.setLayoutDirection(Qt.RightToLeft)
        self.ar_stream_edit.setReadOnly(True)
        ar_stream_layout.addWidget(self.ar_stream_edit)
        stream_splitter.addWidget(ar_stream_frame)

        layout.addWidget(stream_splitter)

    def load_books_and_glossaries(self):
        # Refresh Books
        self.book_combo.clear()
        books = self.book_repo.list_books()
        self._books = books
        for b in books:
            self.book_combo.addItem(f"{b.metadata.title} ({b.source_format.upper()})", b.id)

        # Refresh Glossaries
        self.glossary_combo.clear()
        self.glossary_combo.addItem("None (No glossary rules)", "")
        glossaries = self.glossary_repo.list_profiles()
        for g in glossaries:
            self.glossary_combo.addItem(f"{g.name} ({g.genre} - {len(g.terms)} terms)", g.id)

    def set_active_book(self, book: Book):
        self.load_books_and_glossaries()
        for idx in range(self.book_combo.count()):
            if self.book_combo.itemData(idx) == book.id:
                self.book_combo.setCurrentIndex(idx)
                break
        self.current_book = book
        self._check_existing_job()

    def _on_book_changed(self):
        book_id = self.book_combo.currentData()
        if book_id:
            self.current_book = self.book_repo.get_book(book_id)
            self._check_existing_job()

    def _check_existing_job(self):
        if not self.current_book:
            return
        jobs = self.job_repo.list_jobs()
        matching = [j for j in jobs if j.book_id == self.current_book.id]
        if matching:
            self.current_job = matching[0]
            self.progress_bar.setValue(int(self.current_job.progress_percent))
            self.lbl_progress_status.setText(
                f"Existing Job Found: {self.current_job.status.value.upper()} - {self.current_job.completed_segments}/{self.current_job.total_segments} segments"
            )
            if self.current_job.status == JobStatus.COMPLETED:
                self.export_btn.setEnabled(True)
                self.start_btn.setText("Retranslate Book")
            elif self.current_job.status in (JobStatus.PAUSED, JobStatus.RUNNING, JobStatus.FAILED):
                self.start_btn.setText("Resume Translation")
        else:
            self.current_job = None
            self.progress_bar.setValue(0)
            self.start_btn.setText("Start Full Translation")

    def _on_preview_sample(self):
        if not self.current_book or not self.current_book.chapters:
            QMessageBox.warning(self, "No Book Selected", "Please select a book with chapters first.")
            return

        # Pick first 2-3 translatable blocks from chapter 1
        ch = self.current_book.chapters[0]
        translatable = ch.translatable_blocks()
        if not translatable:
            QMessageBox.warning(self, "Empty Chapter", "First chapter has no translatable text.")
            return

        sample_blocks = translatable[:3]
        sample_text = "\n\n".join(b.source_text for b in sample_blocks)

        glossary_id = self.glossary_combo.currentData()
        profile = self.glossary_repo.get_profile(glossary_id) if glossary_id else GlossaryProfile()

        style_val = self.style_combo.currentData()
        style_type = TranslationStyleType(style_val)

        pref_provider_val = self.provider_combo.currentData()
        preferred_provider = None if pref_provider_val == "auto" else ProviderType(pref_provider_val)

        # Run preview synchronously / fast async
        async def run_preview():
            pipeline = TranslationPipeline()
            seg = Segment(
                job_id="preview",
                chapter_id=ch.id,
                source_text=sample_text,
            )
            return await pipeline.translate_segment(
                segment=seg,
                context_before="",
                context_after="",
                glossary_profile=profile,
                style_type=style_type,
                preferred_provider=preferred_provider,
            )

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(run_preview())
            if result.success:
                dlg = PreviewDialog(sample_text, result.translated_text, self)
                dlg.exec()
            else:
                QMessageBox.critical(self, "Preview Failed", f"Translation error:\n{result.error}")
        finally:
            loop.close()

    def _on_start_or_resume(self):
        if not self.current_book:
            QMessageBox.warning(self, "No Book", "Please select a book first.")
            return

        if not self.current_job or self.current_job.status in (JobStatus.COMPLETED, JobStatus.FAILED):
            style_val = self.style_combo.currentData()
            glossary_id = self.glossary_combo.currentData()
            self.current_job = TranslationJob(
                book_id=self.current_book.id,
                book_title=self.current_book.metadata.title,
                style=TranslationStyleType(style_val),
                glossary_profile_id=glossary_id if glossary_id else None,
                output_format=self.format_combo.currentText().lower(),
            )
            self.job_repo.create_job(self.current_job)

        self.start_btn.setEnabled(False)
        self.pause_btn.setEnabled(True)
        self.export_btn.setEnabled(False)
        self.lbl_progress_status.setText("Translating chapters...")

        # Launch in background worker thread
        self.worker = AsyncWorker(lambda: self.job_runner.run_job(self.current_job.id))
        self.worker.progress_signal.connect(self._on_progress_ui_update)
        self.worker.finished_signal.connect(self._on_job_finished)
        self.worker.start()

    def _on_pause(self):
        if self.job_runner:
            self.job_runner.pause()
            self.pause_btn.setEnabled(False)
            self.start_btn.setEnabled(True)
            self.start_btn.setText("Resume Translation")
            self.lbl_progress_status.setText("Job Paused.")

    def _on_job_progress(self, job: TranslationJob, segment: Optional[Segment]):
        if self.worker:
            self.worker.progress_signal.emit(job, segment)

    def _on_progress_ui_update(self, job: TranslationJob, segment: Optional[Segment]):
        self.current_job = job
        self.progress_bar.setValue(int(job.progress_percent))
        self.lbl_progress_status.setText(
            f"Translating: {job.current_chapter_title} — {job.progress_percent:.1f}%"
        )
        self.lbl_stat_segments.setText(f"Segments: {job.completed_segments} / {job.total_segments}")
        self.lbl_stat_cached.setText(f"Cached: {job.cached_segments}")
        self.lbl_stat_tokens.setText(f"Tokens: {job.total_tokens_used:,}")

        if segment:
            if segment.provider_used:
                self.lbl_stat_provider.setText(f"Active: {segment.provider_used} ({segment.model_used})")
            self.src_stream_edit.setPlainText(segment.source_text)
            if segment.translated_text:
                self.ar_stream_edit.setPlainText(segment.translated_text)

    def _on_job_finished(self, success: bool, message: str):
        self.start_btn.setEnabled(True)
        self.pause_btn.setEnabled(False)
        if success:
            self.export_btn.setEnabled(True)
            self.lbl_progress_status.setText("Translation Complete! Ready to export.")
            QMessageBox.information(self, "Translation Finished", "Book translation completed successfully!")
        else:
            self.lbl_progress_status.setText(f"Job Stopped: {message}")
            QMessageBox.warning(self, "Job Incomplete", f"Translation ended:\n{message}")

    def _on_export_book(self):
        if not self.current_book:
            return
        # Load fresh book data with all translations
        book = self.book_repo.get_book(self.current_book.id)
        fmt = self.format_combo.currentText().lower()

        default_name = f"{book.metadata.title}_Arabic.{fmt}"
        filter_str = "EPUB Files (*.epub)" if fmt == "epub" else "PDF Files (*.pdf)"
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export Translated Book", str(settings.exports_dir / default_name), filter_str
        )
        if not file_path:
            return

        try:
            out_p = Path(file_path)
            if fmt == "epub":
                self.epub_renderer.render(book, out_p)
            else:
                self.pdf_renderer.render(book, out_p)
            QMessageBox.information(
                self, "Export Success", f"Successfully exported translated {fmt.upper()} to:\n{out_p}"
            )
        except Exception as ex:
            QMessageBox.critical(self, "Export Error", f"Failed to render document:\n{str(ex)}")
