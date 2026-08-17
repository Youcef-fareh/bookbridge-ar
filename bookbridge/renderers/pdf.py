"""Arabic RTL PDF Renderer and Exporter."""

import logging
from pathlib import Path
import fitz  # PyMuPDF
from bookbridge.config.constants import BlockType
from bookbridge.models.book import Book
from bookbridge.renderers.base import DocumentRenderer

logger = logging.getLogger(__name__)


class PdfRenderer(DocumentRenderer):
    def render(self, book: Book, output_path: Path) -> Path:
        logger.info(f"Rendering Arabic PDF to: {output_path}")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        doc = fitz.open()

        # A4 page size
        PAGE_WIDTH = 595
        PAGE_HEIGHT = 842
        MARGIN_X = 50
        MARGIN_TOP = 60
        MARGIN_BOTTOM = 60
        USABLE_WIDTH = PAGE_WIDTH - 2 * MARGIN_X

        # Standard font
        for ch in book.chapters:
            page = doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
            y = MARGIN_TOP

            # Insert chapter title
            title_text = ch.title
            rect_title = fitz.Rect(MARGIN_X, y, PAGE_WIDTH - MARGIN_X, y + 25)
            page.insert_textbox(
                rect_title,
                title_text,
                fontsize=16,
                fontname="helv",
                align=fitz.TEXT_ALIGN_RIGHT,
            )
            y += 35

            for blk in ch.blocks:
                if y > PAGE_HEIGHT - MARGIN_BOTTOM - 40:
                    page = doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
                    y = MARGIN_TOP

                if blk.type == BlockType.IMAGE:
                    if blk.resource_id and blk.resource_id in book.resources:
                        res = book.resources[blk.resource_id]
                        if res.data:
                            img_rect = fitz.Rect(MARGIN_X, y, PAGE_WIDTH - MARGIN_X, min(y + 200, PAGE_HEIGHT - MARGIN_BOTTOM))
                            try:
                                page.insert_image(img_rect, stream=res.data)
                                y += 220
                            except Exception:
                                pass
                    continue

                text = blk.translated_text if blk.translated_text else blk.source_text
                if not text:
                    continue

                is_heading = blk.type == BlockType.HEADING
                fsize = 14 if is_heading else 11

                # Render text
                rect = fitz.Rect(MARGIN_X, y, PAGE_WIDTH - MARGIN_X, PAGE_HEIGHT - MARGIN_BOTTOM)
                rc = page.insert_textbox(
                    rect,
                    text,
                    fontsize=fsize,
                    fontname="helv",
                    align=fitz.TEXT_ALIGN_RIGHT,
                )
                # Approximate line height increment
                lines_est = max(1, len(text) // 50 + text.count("\n"))
                y += lines_est * (fsize + 6) + 10

        doc.save(str(output_path))
        doc.close()
        logger.info(f"Arabic PDF successfully written: {output_path}")
        return output_path
