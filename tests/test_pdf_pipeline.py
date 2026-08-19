"""Tests for PDF Parser and Arabic PDF Renderer."""

from pathlib import Path
import fitz
from bookbridge.config.constants import BlockType
from bookbridge.documents.pdf.parser import PdfParser
from bookbridge.models.book import Book, BookMetadata, Chapter, Block
from bookbridge.renderers.pdf import PdfRenderer


def create_sample_pdf(file_path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text(fitz.Point(50, 80), "Chapter 1: The Mountain Peak", fontsize=16)
    page.insert_text(
        fitz.Point(50, 120),
        "The water flowed down the mountain into the silent valley below.",
        fontsize=12,
    )
    doc.save(str(file_path))
    doc.close()


def test_pdf_parsing_and_rendering(tmp_path: Path):
    sample_pdf_path = tmp_path / "sample.pdf"
    create_sample_pdf(sample_pdf_path)

    # Parse PDF
    parser = PdfParser()
    book = parser.parse(sample_pdf_path)

    assert len(book.chapters) >= 1
    assert book.total_translatable_blocks() >= 2

    # Translate
    for ch in book.chapters:
        for blk in ch.blocks:
            if blk.has_translatable_text:
                blk.translated_text = f"نص مترجم: {blk.source_text}"

    # Render translated PDF
    output_pdf_path = tmp_path / "translated.pdf"
    renderer = PdfRenderer()
    renderer.render(book, output_pdf_path)

    assert output_pdf_path.exists()
    assert output_pdf_path.stat().st_size > 0

    # Verify readable with PyMuPDF
    res_doc = fitz.open(str(output_pdf_path))
    assert len(res_doc) >= 1
    pixmap = res_doc[0].get_pixmap()
    assert sum(pixmap.samples) < len(pixmap.samples) * 255
    res_doc.close()


def test_pdf_parser_skips_overlapping_duplicate_text_blocks(tmp_path: Path):
    source_path = tmp_path / "duplicate_layers.pdf"
    doc = fitz.open()
    page = doc.new_page()
    for _ in range(3):
        page.insert_text(fitz.Point(50, 80), "The same paragraph", fontsize=12)
    page.insert_text(fitz.Point(50, 120), "The same paragraph", fontsize=12)
    doc.save(str(source_path))
    doc.close()

    book = PdfParser().parse(source_path)

    assert len(book.chapters) == 1
    assert [block.source_text for block in book.chapters[0].blocks] == [
        "The same paragraph",
        "The same paragraph",
    ]
