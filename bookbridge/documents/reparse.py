"""Rebuild previously imported books after their block granularity changes."""

from collections import defaultdict
from pathlib import Path
from typing import List, Tuple

from bookbridge.database.repositories.book_repo import BookRepository
from bookbridge.database.repositories.job_repo import JobRepository
from bookbridge.documents.epub.parser import EpubParser
from bookbridge.documents.pdf.parser import PdfParser
from bookbridge.models.book import Book


def _preserve_matching_content(previous: Book, updated: Book) -> None:
    updated.id = previous.id
    old_chapters = {
        (chapter.order_index, chapter.source_file_path): chapter
        for chapter in previous.chapters
    }
    old_by_order = {chapter.order_index: chapter for chapter in previous.chapters}

    for chapter in updated.chapters:
        old_chapter = old_chapters.get(
            (chapter.order_index, chapter.source_file_path)
        ) or old_by_order.get(chapter.order_index)
        if old_chapter is None:
            continue

        chapter.id = old_chapter.id
        chapter.book_id = updated.id
        old_blocks = defaultdict(list)
        for block in old_chapter.blocks:
            old_blocks[(block.type.value, block.source_text)].append(block)

        for block in chapter.blocks:
            block.chapter_id = chapter.id
            candidates = old_blocks[(block.type.value, block.source_text)]
            if candidates:
                previous_block = candidates.pop(0)
                block.id = previous_block.id
                block.translated_text = previous_block.translated_text


def reparse_books(
    book_ids: List[str],
    epub_granularity: str,
    pdf_granularity: str,
) -> Tuple[int, List[str]]:
    """Reparse the requested books and report per-book failures."""
    book_repo = BookRepository()
    job_repo = JobRepository()
    updated_count = 0
    errors = []

    for book_id in book_ids:
        previous = book_repo.get_book(book_id)
        if previous is None:
            errors.append(f"{book_id}: no longer exists")
            continue

        source_path = Path(previous.source_file_path)
        if not source_path.is_file():
            errors.append(f"{previous.metadata.title}: source file is missing ({source_path})")
            continue

        try:
            if previous.source_format == "epub":
                updated = EpubParser(epub_granularity).parse(source_path)
            elif previous.source_format == "pdf":
                updated = PdfParser(pdf_granularity).parse(source_path)
            else:
                errors.append(
                    f"{previous.metadata.title}: unsupported format {previous.source_format}"
                )
                continue

            _preserve_matching_content(previous, updated)
            book_repo.replace_book(updated)
            job_repo.reset_incomplete_jobs_for_book(book_id)
            updated_count += 1
        except Exception as exc:
            errors.append(f"{previous.metadata.title}: {exc}")

    return updated_count, errors
