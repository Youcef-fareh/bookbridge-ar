"""Regression tests for bugs found during the BookBridge audit."""

from pathlib import Path

import fitz
import pytest

from bookbridge.config.constants import CredentialState, JobStatus, ProviderType
from bookbridge.database.connection import DatabaseManager
from bookbridge.database.repositories.book_repo import BookRepository
from bookbridge.database.repositories.credential_repo import CredentialRepository
from bookbridge.database.repositories.glossary_repo import GlossaryRepository
from bookbridge.database.repositories.job_repo import JobRepository
from bookbridge.engine.job_runner import JobRunner
from bookbridge.engine.translator import TranslationPipeline
from bookbridge.models.book import Block, Book, BookMetadata, Chapter
from bookbridge.models.job import TranslationJob
from bookbridge.models.provider import ProviderCredentialMetadata
from bookbridge.providers.mock import MockProvider
from bookbridge.renderers.pdf import PdfRenderer
from bookbridge.routing.router import TranslationRouter
from bookbridge.security.keyring_manager import keyring_manager
from bookbridge.ui.web_bridge import _tail_lines


def test_tail_lines_keeps_traceback_continuations(tmp_path: Path):
    log_path = tmp_path / "bookbridge.log"
    log_path.write_text(
        "\n".join(
            [
                "2026-01-01 10:00:00 | INFO | bookbridge.test | job started",
                "2026-01-01 10:00:01 | ERROR | bookbridge.test | translation crashed",
                "Traceback (most recent call last):",
                '  File "worker.py", line 10, in run',
                "ValueError: provider returned an empty response",
                "2026-01-01 10:00:02 | INFO | bookbridge.test | worker exited",
            ]
        ),
        encoding="utf-8",
    )

    error_lines = _tail_lines(log_path, max_lines=100, level="ERROR")

    assert "translation crashed" in "\n".join(error_lines)
    assert "Traceback (most recent call last):" in error_lines
    assert "ValueError: provider returned an empty response" in error_lines
    assert not any("job started" in line for line in error_lines)
    assert not any("worker exited" in line for line in error_lines)


def test_pdf_renderer_paginates_long_paragraph(tmp_path: Path):
    book = Book(
        metadata=BookMetadata(title="Long Paragraph Book"),
        source_format="pdf",
    )
    chapter = Chapter(book_id=book.id, title="Chapter 1", order_index=0)
    long_text = ("overflowing paragraph content " * 400) + "FINALTOKEN"
    chapter.blocks.append(
        Block(
            chapter_id=chapter.id,
            source_text=long_text,
            translated_text=long_text,
            order_index=0,
        )
    )
    book.chapters.append(chapter)

    output_path = tmp_path / "long.pdf"
    PdfRenderer().render(book, output_path)

    doc = fitz.open(str(output_path))
    try:
        extracted = "\n".join(page.get_text() for page in doc)
        assert len(doc) >= 2, "long paragraph should continue on another page"
        assert "FINALTOKEN" in extracted, "tail of the paragraph was dropped"
    finally:
        doc.close()


def test_database_managers_do_not_share_thread_local_connections(tmp_path: Path):
    first = DatabaseManager(tmp_path / "first.db")
    second = DatabaseManager(tmp_path / "second.db")
    try:
        first_connection = first.get_connection()
        second_connection = second.get_connection()
        assert first_connection is not second_connection
        first_file = first_connection.execute("PRAGMA database_list").fetchone()[2]
        second_file = second_connection.execute("PRAGMA database_list").fetchone()[2]
        assert Path(first_file) == tmp_path / "first.db"
        assert Path(second_file) == tmp_path / "second.db"
    finally:
        first.close()
        second.close()


def test_recover_orphaned_jobs_marks_them_paused():
    book = Book(metadata=BookMetadata(title="Orphaned Job Book"), source_format="epub")
    BookRepository().save_book(book)
    job = TranslationJob(
        book_id=book.id,
        book_title=book.metadata.title,
        status=JobStatus.RUNNING,
    )
    job_repo = JobRepository()
    job_repo.create_job(job)

    recovered = job_repo.recover_orphaned_jobs()

    stored = job_repo.get_job(job.id)
    assert recovered >= 1
    assert stored is not None
    assert stored.status == JobStatus.PAUSED
    assert "Interrupted" in (stored.error_message or "")


@pytest.mark.asyncio
async def test_resume_clears_failed_segment_counters():
    book_repo = BookRepository()
    job_repo = JobRepository()
    glossary_repo = GlossaryRepository()
    cred_repo = CredentialRepository()

    cred = ProviderCredentialMetadata(
        id="cred_resume_regression_test",
        provider=ProviderType.MOCK,
        name="Resume Regression Mock Key",
    )
    cred_repo.save_credential_metadata(cred)
    keyring_manager.save_secret(cred.id, "dummy_secret")

    router = TranslationRouter(cred_repo)
    mock_provider = MockProvider(failure_mode="auth_error")
    router.register_provider(ProviderType.MOCK, mock_provider)
    pipeline = TranslationPipeline(router=router)

    book = Book(
        metadata=BookMetadata(title="Resume Regression Book", author="Tester"),
        source_format="epub",
        source_file_path="dummy.epub",
    )
    chapter = Chapter(book_id=book.id, title="Chapter 1", order_index=0)
    chapter.blocks.append(
        Block(
            chapter_id=chapter.id,
            source_text="This segment fails once, then succeeds on resume.",
            order_index=0,
        )
    )
    book.chapters.append(chapter)
    book_repo.save_book(book)

    job = TranslationJob(book_id=book.id, book_title=book.metadata.title)
    job_repo.create_job(job)
    runner = JobRunner(job_repo, book_repo, glossary_repo, pipeline)

    assert await runner.run_job(job.id) is False
    failed_job = job_repo.get_job(job.id)
    assert failed_job.status == JobStatus.NEEDS_REVIEW
    assert failed_job.failed_segments == 1
    assert failed_job.completed_segments == 0

    # The auth failure put the credential into an unavailable state in the
    # previous run. Re-enable it and let the mock provider succeed.
    credential = cred_repo.get_credential(cred.id)
    assert credential is not None
    credential.state = CredentialState.AVAILABLE
    credential.consecutive_failures = 0
    cred_repo.save_credential_metadata(credential)
    mock_provider.failure_mode = None

    assert await runner.run_job(job.id) is True
    resumed_job = job_repo.get_job(job.id)
    assert resumed_job.status == JobStatus.COMPLETED
    assert resumed_job.failed_segments == 0
    assert resumed_job.completed_segments == resumed_job.total_segments
    assert resumed_job.error_message is None
    assert job_repo.get_provider_models([job.id])[job.id] == (
        ProviderType.MOCK.value,
        "mock-model-v1",
    )
