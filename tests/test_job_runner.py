"""Tests for Job Runner, State Persistence, and Resume Capability."""

import pytest
from bookbridge.config.constants import BlockType, JobStatus, ProviderType, SegmentStatus
from bookbridge.database.repositories.book_repo import BookRepository
from bookbridge.database.repositories.credential_repo import CredentialRepository
from bookbridge.database.repositories.glossary_repo import GlossaryRepository
from bookbridge.database.repositories.job_repo import JobRepository
from bookbridge.engine.job_runner import JobRunner
from bookbridge.engine.translator import TranslationPipeline
from bookbridge.models.book import Book, BookMetadata, Chapter, Block
from bookbridge.models.job import TranslationJob
from bookbridge.models.provider import ProviderCredentialMetadata
from bookbridge.providers.mock import MockProvider
from bookbridge.routing.router import TranslationRouter
from bookbridge.security.keyring_manager import keyring_manager
from bookbridge.segmentation.engine import SegmentationEngine
from bookbridge.config.settings import settings


@pytest.mark.asyncio
async def test_job_runner_execution_and_resume():
    book_repo = BookRepository()
    job_repo = JobRepository()
    glossary_repo = GlossaryRepository()
    cred_repo = CredentialRepository()

    # Save mock credential
    cred = ProviderCredentialMetadata(
        id="cred_job_runner_test",
        provider=ProviderType.MOCK,
        name="Job Runner Mock Key",
    )
    cred_repo.save_credential_metadata(cred)
    keyring_manager.save_secret(cred.id, "dummy_secret")

    # Set up router & pipeline
    router = TranslationRouter(cred_repo)
    mock_provider = MockProvider()
    router.register_provider(ProviderType.MOCK, mock_provider)
    pipeline = TranslationPipeline(router=router)

    # Create test book with 2 chapters, 3 paragraphs each
    book = Book(
        metadata=BookMetadata(title="Test Job Book", author="Tester"),
        source_format="epub",
        source_file_path="dummy.epub",
    )
    for c_idx in range(2):
        ch = Chapter(book_id=book.id, title=f"Chapter {c_idx + 1}", order_index=c_idx)
        for b_idx in range(3):
            ch.blocks.append(
                Block(
                    chapter_id=ch.id,
                    source_text=f"This is paragraph {b_idx + 1} of Chapter {c_idx + 1}.",
                    order_index=b_idx,
                )
            )
        book.chapters.append(ch)

    book_repo.save_book(book)

    # Create job
    job = TranslationJob(
        book_id=book.id,
        book_title=book.metadata.title,
    )
    job_repo.create_job(job)

    runner = JobRunner(job_repo, book_repo, glossary_repo, pipeline)

    # Execute job
    success = await runner.run_job(job.id)
    assert success is True

    # Verify job status
    finished_job = job_repo.get_job(job.id)
    assert finished_job.status == JobStatus.COMPLETED
    assert finished_job.completed_segments == finished_job.total_segments

    # Verify resume behavior: running again should not retranslate
    initial_calls = mock_provider.call_count
    success_resume = await runner.run_job(job.id)
    assert success_resume is True
    # No extra translations needed because all segments were already translated!
    assert mock_provider.call_count == initial_calls


@pytest.mark.asyncio
async def test_failed_segments_do_not_complete_job():
    book_repo = BookRepository()
    job_repo = JobRepository()
    glossary_repo = GlossaryRepository()
    cred_repo = CredentialRepository()

    cred = ProviderCredentialMetadata(
        id="cred_job_runner_failure_test",
        provider=ProviderType.MOCK,
        name="Job Runner Failure Mock Key",
    )
    cred_repo.save_credential_metadata(cred)
    keyring_manager.save_secret(cred.id, "dummy_secret")

    router = TranslationRouter(cred_repo)
    router.register_provider(ProviderType.MOCK, MockProvider(failure_mode="auth_error"))
    pipeline = TranslationPipeline(router=router)

    book = Book(
        metadata=BookMetadata(title="Failed Job Book", author="Tester"),
        source_format="epub",
        source_file_path="dummy.epub",
    )
    chapter = Chapter(book_id=book.id, title="Chapter 1", order_index=0)
    chapter.blocks.append(
        Block(chapter_id=chapter.id, source_text="This cannot be translated.", order_index=0)
    )
    book.chapters.append(chapter)
    book_repo.save_book(book)

    job = TranslationJob(book_id=book.id, book_title=book.metadata.title)
    job_repo.create_job(job)
    runner = JobRunner(job_repo, book_repo, glossary_repo, pipeline)

    assert await runner.run_job(job.id) is False

    finished_job = job_repo.get_job(job.id)
    assert finished_job.status == JobStatus.NEEDS_REVIEW
    assert finished_job.failed_segments == 1
    assert finished_job.completed_segments == 0


def test_segmentation_skips_whitespace_only_blocks():
    book = Book(metadata=BookMetadata(title="Blank Block Book"), source_format="epub")
    chapter = Chapter(book_id=book.id, title="Chapter 1", order_index=0)
    chapter.blocks.extend(
        [
            Block(chapter_id=chapter.id, source_text="   \n\t", order_index=0),
            Block(chapter_id=chapter.id, source_text="Visible text", order_index=1),
        ]
    )

    segments = SegmentationEngine().segment_chapter(chapter, "job-id")

    assert len(segments) == 1
    assert segments[0].source_text == "Visible text"


def test_job_runner_uses_saved_segmentation_settings():
    original_max_chars = settings.max_segment_chars
    original_context_blocks = settings.context_window_blocks
    try:
        settings.max_segment_chars = 321
        settings.context_window_blocks = 4
        runner = JobRunner()

        assert runner.segmenter.max_chars == 321
        assert runner.segmenter.context_blocks_count == 4
    finally:
        settings.max_segment_chars = original_max_chars
        settings.context_window_blocks = original_context_blocks


@pytest.mark.asyncio
async def test_new_job_reads_segmentation_settings_at_execution_time():
    original_max_chars = settings.max_segment_chars
    original_context_blocks = settings.context_window_blocks
    try:
        settings.max_segment_chars = 1200
        settings.context_window_blocks = 2
        runner = JobRunner()

        settings.max_segment_chars = 333
        settings.context_window_blocks = 5
        book = Book(
            metadata=BookMetadata(title="Settings Timing Book"),
            source_format="epub",
            source_file_path="dummy.epub",
        )
        chapter = Chapter(book_id=book.id, title="Chapter 1", order_index=0)
        chapter.blocks.append(Block(chapter_id=chapter.id, source_text="Text", order_index=0))
        book.chapters.append(chapter)
        BookRepository().save_book(book)

        job = TranslationJob(book_id=book.id, book_title=book.metadata.title)
        JobRepository().create_job(job)
        await runner.run_job(job.id)

        assert runner.segmenter.max_chars == 333
        assert runner.segmenter.context_blocks_count == 5
    finally:
        settings.max_segment_chars = original_max_chars
        settings.context_window_blocks = original_context_blocks


@pytest.mark.asyncio
async def test_job_runner_cancel_persists_cancelled_status():
    book_repo = BookRepository()
    job_repo = JobRepository()
    glossary_repo = GlossaryRepository()
    cred_repo = CredentialRepository()

    cred = ProviderCredentialMetadata(
        id="cred_job_runner_cancel_test",
        provider=ProviderType.MOCK,
        name="Job Runner Cancel Mock Key",
    )
    cred_repo.save_credential_metadata(cred)
    keyring_manager.save_secret(cred.id, "dummy_secret")

    router = TranslationRouter(cred_repo)
    router.register_provider(ProviderType.MOCK, MockProvider())
    pipeline = TranslationPipeline(router=router)

    book = Book(
        metadata=BookMetadata(title="Cancelled Job Book", author="Tester"),
        source_format="epub",
        source_file_path="dummy.epub",
    )
    chapter = Chapter(book_id=book.id, title="Chapter 1", order_index=0)
    chapter.blocks.extend(
        [
            Block(
                chapter_id=chapter.id,
                source_text="First paragraph.",
                order_index=0,
                type=BlockType.HEADING,
            ),
            Block(chapter_id=chapter.id, source_text="Second paragraph.", order_index=1),
        ]
    )
    book.chapters.append(chapter)
    book_repo.save_book(book)

    job = TranslationJob(book_id=book.id, book_title=book.metadata.title)
    job_repo.create_job(job)
    runner = JobRunner(job_repo, book_repo, glossary_repo, pipeline)

    def cancel_after_first_segment(updated_job, segment):
        if segment and updated_job.completed_segments == 1:
            runner.cancel()

    runner.set_progress_callback(cancel_after_first_segment)

    assert await runner.run_job(job.id) is False

    cancelled_job = job_repo.get_job(job.id)
    assert cancelled_job.status == JobStatus.CANCELLED
    assert cancelled_job.completed_segments == 1
