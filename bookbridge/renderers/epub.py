"""Arabic RTL EPUB Renderer and Exporter.

Creates compliant EPUB 3 / EPUB 2 documents with RTL Arabic styling,
preserved images, chapters, and metadata.
"""

import html
import logging
from pathlib import Path
import ebooklib
from ebooklib import epub
from bookbridge.config.constants import BlockType
from bookbridge.models.book import Book
from bookbridge.renderers.base import DocumentRenderer

logger = logging.getLogger(__name__)

ARABIC_EPUB_CSS = """
@charset "utf-8";

html, body {
    direction: rtl;
    unicode-bidi: embed;
    text-align: right;
    font-family: "Amiri", "Scheherazade New", "Noto Naskh Arabic", "Traditional Arabic", "Segoe UI", Arial, sans-serif;
    font-size: 1.05em;
    line-height: 1.8;
    margin: 1em;
    padding: 0;
    color: #1a1a1a;
}

h1, h2, h3, h4, h5, h6 {
    text-align: right;
    direction: rtl;
    line-height: 1.4;
    margin-top: 1.2em;
    margin-bottom: 0.6em;
    color: #0f172a;
}

h1 { font-size: 1.7em; }
h2 { font-size: 1.4em; }
h3 { font-size: 1.2em; }

p {
    text-indent: 1.5em;
    margin: 0.6em 0;
    text-align: justify;
    text-justify: inter-word;
}

blockquote {
    margin: 1em 2em;
    padding-right: 1em;
    border-right: 4px solid #6366f1;
    font-style: italic;
    color: #4b5563;
}

img {
    max-width: 100%;
    height: auto;
    display: block;
    margin: 1.5em auto;
}

ul, ol {
    padding-right: 2em;
    margin: 0.8em 0;
}

li {
    margin-bottom: 0.4em;
}

.center-image {
    text-align: center;
    margin: 1.5em 0;
}
"""


class EpubRenderer(DocumentRenderer):
    def render(self, book: Book, output_path: Path) -> Path:
        logger.info(f"Rendering Arabic EPUB to: {output_path}")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        epub_book = epub.EpubBook()

        # Metadata
        epub_book.set_identifier(book.metadata.identifier or f"bookbridge-{book.id}")
        epub_book.set_title(book.metadata.title)
        epub_book.set_language("ar")
        epub_book.add_author(book.metadata.author)

        if book.metadata.description:
            epub_book.add_metadata("DC", "description", book.metadata.description)
        if book.metadata.publisher:
            epub_book.add_metadata("DC", "publisher", book.metadata.publisher)

        # Add CSS
        css_item = epub.EpubItem(
            uid="style_arabic",
            file_name="style/arabic.css",
            media_type="text/css",
            content=ARABIC_EPUB_CSS.encode("utf-8"),
        )
        epub_book.add_item(css_item)

        # Add Images / Resources
        image_items_map = {}
        for res_id, res in book.resources.items():
            if res.data:
                img_item = epub.EpubItem(
                    uid=res.id,
                    file_name=res.file_name if not res.file_name.startswith("images/") else res.file_name,
                    media_type=res.media_type,
                    content=res.data,
                )
                epub_book.add_item(img_item)
                image_items_map[res_id] = img_item

        # Create Chapters
        epub_chapters = []
        toc_items = []

        for ch_idx, ch in enumerate(book.chapters):
            ch_item = epub.EpubHtml(
                title=ch.title,
                file_name=f"chapter_{ch_idx + 1:04d}.xhtml",
                lang="ar",
            )
            ch_item.direction = "rtl"
            ch_item.add_item(css_item)

            # Build HTML content
            html_parts = [
                '<?xml version="1.0" encoding="utf-8"?>',
                '<!DOCTYPE html>',
                '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" dir="rtl" xml:lang="ar" lang="ar">',
                '<head>',
                f'<title>{html.escape(ch.title)}</title>',
                '<link rel="stylesheet" type="text/css" href="style/arabic.css" />',
                '</head>',
                '<body dir="rtl">',
            ]

            for block in ch.blocks:
                text_to_render = block.translated_text if block.translated_text else block.source_text
                escaped_text = html.escape(text_to_render)

                if block.type == BlockType.HEADING:
                    html_parts.append(f"<h2>{escaped_text}</h2>")
                elif block.type == BlockType.QUOTE:
                    html_parts.append(f"<blockquote><p>{escaped_text}</p></blockquote>")
                elif block.type == BlockType.LIST:
                    html_parts.append(f"<ul><li>{escaped_text}</li></ul>")
                elif block.type == BlockType.IMAGE:
                    if block.resource_id and block.resource_id in image_items_map:
                        img_name = image_items_map[block.resource_id].file_name
                        html_parts.append(f'<div class="center-image"><img src="{img_name}" alt="Illustration" /></div>')
                elif block.type == BlockType.PAGE_BREAK:
                    html_parts.append("<hr />")
                else:
                    # Paragraph: split multiple lines with <br/> or <p>
                    paragraphs = [p.strip() for p in escaped_text.split("\n\n") if p.strip()]
                    if not paragraphs and escaped_text:
                        paragraphs = [escaped_text]
                    for p in paragraphs:
                        p_with_breaks = p.replace("\n", "<br/>")
                        html_parts.append(f"<p>{p_with_breaks}</p>")

            html_parts.append("</body></html>")

            ch_item.set_content("\n".join(html_parts).encode("utf-8"))
            epub_book.add_item(ch_item)
            epub_chapters.append(ch_item)
            toc_items.append(ch_item)

        # Set TOC and Spine
        epub_book.toc = tuple(toc_items)
        epub_book.add_item(epub.EpubNcx())
        epub_book.add_item(epub.EpubNav())

        epub_book.spine = ["nav"] + epub_chapters

        # Write output file
        epub.write_epub(str(output_path), epub_book, {})
        logger.info(f"Arabic EPUB successfully written: {output_path}")
        return output_path
