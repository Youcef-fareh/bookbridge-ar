import fitz

from bookbridge.config.constants import JobStatus
from bookbridge.config.settings import AppSettings
from bookbridge.database.repositories.book_repo import BookRepository
from bookbridge.database.repositories.job_repo import JobRepository
from bookbridge.documents.pdf.parser import PdfParser
from bookbridge.documents.reparse import _preserve_matching_content, reparse_books
from bookbridge.models.book import Block, Book, BookMetadata, Chapter
from bookbridge.models.job import Segment, TranslationJob


def test_parser_granularity_settings_persist(tmp_path):
    configured = AppSettings(
        data_dir=tmp_path,
        epub_block_granularity="chapter",
        pdf_block_granularity="page",
    )
    configured.save()

    loaded = AppSettings(data_dir=tmp_path)
    loaded.load()

    assert loaded.epub_block_granularity == "chapter"
    assert loaded.pdf_block_granularity == "page"


def test_reparse_updates_saved_book_and_resets_incomplete_jobs(tmp_path):
    source_path = tmp_path / "existing.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(fitz.Point(50, 80), "Chapter One", fontsize=16)
    page.insert_text(fitz.Point(50, 120), "A paragraph from the existing book.", fontsize=12)
    doc.save(str(source_path))
    doc.close()

    book = PdfParser(granularity="paragraph").parse(source_path)
    book_repo = BookRepository()
    job_repo = JobRepository()
    book_repo.save_book(book)

    job = TranslationJob(
        book_id=book.id,
        book_title=book.metadata.title,
        status=JobStatus.PAUSED,
        total_segments=1,
    )
    job_repo.create_job(job)
    job_repo.save_segments(
        [
            Segment(
                job_id=job.id,
                chapter_id=book.chapters[0].id,
                block_ids=[book.chapters[0].blocks[0].id],
                source_text=book.chapters[0].blocks[0].source_text,
            )
        ]
    )

    updated_count, errors = reparse_books([book.id], "paragraph", "page")

    updated = book_repo.get_book(book.id)
    reset_job = job_repo.get_job(job.id)
    assert updated_count == 1
    assert errors == []
    assert updated is not None
    assert len(updated.chapters[0].blocks) == 1
    assert updated.chapters[0].blocks[0].type.value == "paragraph"
    assert reset_job is not None
    assert reset_job.status == JobStatus.QUEUED
    assert reset_job.total_segments == 0
    assert job_repo.get_job_segments(job.id) == []


def test_reparse_preserves_translation_for_exact_matching_blocks():
    original = Book(
        id="book-id",
        metadata=BookMetadata(),
        chapters=[
            Chapter(
                id="chapter-id",
                book_id="book-id",
                order_index=0,
                blocks=[
                    Block(
                        id="block-id",
                        chapter_id="chapter-id",
                        source_text="Unchanged source text",
                        translated_text="النص المترجم",
                    )
                ],
            )
        ],
    )
    reparsed = Book(
        metadata=BookMetadata(),
        chapters=[
            Chapter(
                book_id="new-book-id",
                order_index=0,
                blocks=[Block(chapter_id="new-chapter-id", source_text="Unchanged source text")],
            )
        ],
    )

    _preserve_matching_content(original, reparsed)

    assert reparsed.id == "book-id"
    assert reparsed.chapters[0].id == "chapter-id"
    assert reparsed.chapters[0].blocks[0].id == "block-id"
    assert reparsed.chapters[0].blocks[0].translated_text == "النص المترجم"
