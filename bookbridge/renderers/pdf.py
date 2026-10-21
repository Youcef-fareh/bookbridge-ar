"""Arabic RTL PDF Renderer and Exporter."""

import logging
import os
from pathlib import Path
import fitz  # PyMuPDF
import arabic_reshaper
from bidi.algorithm import get_display
from bookbridge.config.constants import BlockType
from bookbridge.models.book import Book
from bookbridge.renderers.base import DocumentRenderer

logger = logging.getLogger(__name__)


def _find_arabic_font() -> str:
    candidates = [
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "tahoma.ttf",
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "arial.ttf",
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    raise RuntimeError("No Arabic-capable font was found. Install Tahoma or Arial.")


def _shape_rtl_text(text: str) -> str:
    return get_display(arabic_reshaper.reshape(text))


class PdfRenderer(DocumentRenderer):
    def render(self, book: Book, output_path: Path) -> Path:
        logger.info(f"Rendering Arabic PDF to: {output_path}")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        doc = fitz.open()
        font_file = _find_arabic_font()

        # A4 page size
        PAGE_WIDTH = 595
        PAGE_HEIGHT = 842
        MARGIN_X = 50
        MARGIN_TOP = 60
        MARGIN_BOTTOM = 60
        USABLE_WIDTH = PAGE_WIDTH - 2 * MARGIN_X

        def new_page():
            return doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)

        def split_text(text: str):
            """Split unshaped text near the middle at a natural boundary."""
            if len(text) <= 1:
                return text, None
            middle = len(text) // 2
            # Prefer a paragraph break, then a line break, then a space.
            boundary = max(
                text.rfind("\n\n", 0, middle),
                text.rfind("\n", 0, middle),
                text.rfind(" ", 0, middle),
            )
            if boundary <= 0:
                boundary = text.find(" ", middle)
                if boundary < 0:
                    boundary = text.find("\n", middle)
            if boundary <= 0:
                # A single very long token (URL, CJK run, etc.). Character
                # splitting guarantees forward progress.
                return text[:middle], text[middle:]
            return text[:boundary].rstrip(), text[boundary + 1:].lstrip()

        def insert_text(page, y: float, text: str, fontsize: float, heading: bool = False):
            """Draw a text block and paginate instead of silently dropping text.

            ``insert_textbox`` writes nothing and returns a negative value when
            the block does not fit. The old code ignored that return value, so
            any paragraph longer than the remaining page height vanished.
            """
            shaped = _shape_rtl_text(text)
            rect = fitz.Rect(
                MARGIN_X,
                y,
                PAGE_WIDTH - MARGIN_X,
                PAGE_HEIGHT - MARGIN_BOTTOM,
            )
            rc = page.insert_textbox(
                rect,
                shaped,
                fontsize=fontsize,
                fontname="arabic",
                fontfile=font_file,
                align=fitz.TEXT_ALIGN_RIGHT,
            )
            if rc >= 0:
                # Positive return value is the unused height in the rectangle.
                used_height = rect.height - rc
                return page, y + used_height + (16 if heading else 10)

            # The block did not fit in the remaining space. If it is already
            # partway down a page, retry the whole block at the top of a fresh
            # page before splitting it. This keeps bidi/shaping context intact
            # for the common "paragraph crosses a page boundary" case.
            if y > MARGIN_TOP + 1:
                return insert_text(new_page(), MARGIN_TOP, text, fontsize, heading)

            first, second = split_text(text)
            if second is None:
                # A single glyph that still will not fit a full page. This is
                # effectively impossible for normal fonts; preserve it anyway.
                logger.warning("Text block could not fit on a page; writing it directly.")
                page.insert_text(
                    (PAGE_WIDTH - MARGIN_X, y + fontsize),
                    shaped,
                    fontsize=fontsize,
                    fontname="arabic",
                    fontfile=font_file,
                )
                return page, y + fontsize * 2 + 6

            page, next_y = insert_text(page, y, first, fontsize, heading)
            return insert_text(page, next_y, second, fontsize, heading)

        # Standard font
        for ch in book.chapters:
            page = new_page()
            y = MARGIN_TOP

            # Insert chapter title (also paginates if unexpectedly long).
            page, y = insert_text(page, y, ch.title, 16, heading=True)

            for blk in ch.blocks:
                if y > PAGE_HEIGHT - MARGIN_BOTTOM - 40:
                    page = new_page()
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
                page, y = insert_text(page, y, text, fsize, heading=is_heading)

        doc.save(str(output_path))
        doc.close()
        logger.info(f"Arabic PDF successfully written: {output_path}")
        return output_path
