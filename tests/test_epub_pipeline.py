"""Tests for EPUB Parsing, Block Extraction, and Arabic RTL EPUB Reconstruction."""

import io
from pathlib import Path
from PIL import Image
import ebooklib
from ebooklib import epub
from bookbridge.documents.epub.parser import EpubParser
from bookbridge.models.book import Book, BookMetadata, Chapter, Block
from bookbridge.renderers.epub import EpubRenderer


def create_sample_epub(file_path: Path) -> None:
    """Generates a synthetic test EPUB containing chapters and an embedded image."""
    book = epub.EpubBook()
    book.set_identifier("test-sample-book-001")
    book.set_title("The Chronicles of Cultivation")
    book.set_language("en")
    book.add_author("Author Master")

    # Generate synthetic image (100x100 RGB)
    img_byte_arr = io.BytesIO()
    image = Image.new("RGB", (100, 100), color=(73, 109, 137))
    image.save(img_byte_arr, format="JPEG")
    img_data = img_byte_arr.getvalue()

    img_item = epub.EpubItem(
        uid="img_cover",
        file_name="images/cover.jpg",
        media_type="image/jpeg",
        content=img_data,
    )
    book.add_item(img_item)

    # Chapter 1
    c1 = epub.EpubHtml(title="Chapter 1: The Mountain", file_name="ch1.xhtml", lang="en")
    c1.content = """
    <html>
    <head><title>Chapter 1</title></head>
    <body>
        <h1>Chapter 1: The Mountain</h1>
        <p>The water flowed through the valley silently.</p>
        <div class="image"><img src="images/cover.jpg" alt="Mountain View"/></div>
        <blockquote><p>A journey of a thousand li begins beneath one's feet.</p></blockquote>
    </body>
    </html>
    """
    book.add_item(c1)

    # Chapter 2
    c2 = epub.EpubHtml(title="Chapter 2: The Spirit", file_name="ch2.xhtml", lang="en")
    c2.content = """
    <html>
    <head><title>Chapter 2</title></head>
    <body>
        <h2>Chapter 2: The Spirit</h2>
        <p>The Sword Spirit opened its eyes after ten thousand years of slumber.</p>
    </body>
    </html>
    """
    book.add_item(c2)

    book.toc = (c1, c2)
    book.spine = ["nav", c1, c2]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    epub.write_epub(str(file_path), book, {})


def test_epub_roundtrip_pipeline(tmp_path: Path):
    sample_epub_path = tmp_path / "sample_source.epub"
    create_sample_epub(sample_epub_path)

    # 1. Parse EPUB
    parser = EpubParser()
    book_model = parser.parse(sample_epub_path)

    assert book_model.metadata.title == "The Chronicles of Cultivation"
    assert len(book_model.chapters) == 2
    assert len(book_model.resources) == 1
    assert book_model.total_translatable_blocks() >= 4

    # 2. Simulate translation of blocks
    for ch in book_model.chapters:
        for blk in ch.blocks:
            if blk.has_translatable_text:
                blk.translated_text = f"ترجمة عربية: {blk.source_text}"

    # 3. Export to Arabic EPUB
    output_epub_path = tmp_path / "translated_arabic.epub"
    renderer = EpubRenderer()
    renderer.render(book_model, output_epub_path)

    assert output_epub_path.exists()
    assert output_epub_path.stat().st_size > 0

    # 4. Verify output EPUB readability
    exported_epub = epub.read_epub(str(output_epub_path))
    assert exported_epub.get_metadata("DC", "language")[0][0] == "ar"

    # Verify images were preserved
    exported_images = [
        item for item in exported_epub.get_items() if item.get_type() == ebooklib.ITEM_IMAGE
    ]
    assert len(exported_images) == 1
    assert len(exported_images[0].get_content()) > 0


def test_epub_renderer_removes_xml_forbidden_control_characters(tmp_path: Path):
    book = Book(
        metadata=BookMetadata(
            title="Title\x00 with control",
            author="Author\x0b",
            description="Description\x1f",
        ),
        source_format="pdf",
    )
    chapter = Chapter(book_id=book.id, title="Chapter\x00")
    chapter.blocks.append(
        Block(chapter_id=chapter.id, source_text="Text\x00 with\x0b controls")
    )
    book.chapters.append(chapter)

    output_path = tmp_path / "control_chars.epub"
    EpubRenderer().render(book, output_path)

    exported_epub = epub.read_epub(str(output_path))
    assert exported_epub.get_metadata("DC", "title")[0][0] == "Title with control"
