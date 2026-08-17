"""Tests for Job Runner, State Persistence, and Resume Capability."""

import pytest
from bookbridge.config.constants import JobStatus, ProviderType, SegmentStatus
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
