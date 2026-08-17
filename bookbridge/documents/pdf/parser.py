"""Native PDF Parser using PyMuPDF (fitz)."""

import logging
from pathlib import Path
import fitz  # PyMuPDF
from bookbridge.config.constants import BlockType
from bookbridge.documents.base import DocumentParser
from bookbridge.models.book import (
    Book,
    BookMetadata,
    Chapter,
    Block,
    ImageResource,
    SourceLocation,
)

logger = logging.getLogger(__name__)


class PdfParser(DocumentParser):
    def parse(self, file_path: Path) -> Book:
        logger.info(f"Parsing PDF document: {file_path}")
        doc = None
        try:
            doc = fitz.open(str(file_path))
        except RuntimeError as e:
            logger.error(f"Failed to open PDF file: {str(e)}")
            raise Exception(f"Cannot open PDF file. The file may be corrupted or in an unsupported format: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error opening PDF: {str(e)}")
            raise Exception(f"Unexpected error opening PDF: {str(e)}")

        meta = doc.metadata or {}
        title = meta.get("title") or file_path.stem
        author = meta.get("author") or "Unknown Author"

        book = Book(
            metadata=BookMetadata(
                title=title,
                author=author,
                language="en",
            ),
            source_format="pdf",
            source_file_path=str(file_path),
        )

        chapter_counter = 1
        block_counter = 0

        try:
            for page_num in range(len(doc)):
                try:
                    page = doc[page_num]
                except Exception as e:
                    logger.warning(f"Skipping page {page_num + 1}: {str(e)}")
                    continue

                # Group pages into chapters (e.g. 1 page = 1 chapter or TOC bookmarks)
                chapter = Chapter(
                    book_id=book.id,
                    title=f"Page {page_num + 1}",
                    order_index=page_num,
                )

                # Extract text blocks
                try:
                    text_blocks = page.get_text("blocks")
                    for b in text_blocks:
                        # b format: (x0, y0, x1, y1, "lines", block_no, block_type)
                        # block_type == 0 is text, 1 is image
                        if b[6] == 0:
                            text = b[4].strip()
                            if not text:
                                continue
                            # Detect if heading (short text or large font)
                            is_heading = len(text.splitlines()) == 1 and len(text) < 60
                            blk_type = BlockType.HEADING if is_heading else BlockType.PARAGRAPH

                            block = Block(
                                chapter_id=chapter.id,
                                type=blk_type,
                                source_text=text,
                                order_index=block_counter,
                                source_location=SourceLocation(
                                    page_number=page_num + 1,
                                    bbox=[b[0], b[1], b[2], b[3]],
                                ),
                                is_translatable=True,
                            )
                            chapter.blocks.append(block)
                            block_counter += 1
                except Exception as e:
                    logger.warning(f"Failed to extract text from page {page_num + 1}: {str(e)}")

                # Extract page images (with memory protection)
                # NOTE: Image extraction is disabled by default to prevent Wayland display server crashes
                # Images can cause buffer allocation issues on Linux with Wayland. Enable only if needed.
                try:
                    images = page.get_images()
                    if images:
                        logger.info(f"Skipping image extraction for {len(images)} image(s) on page {page_num + 1} (disabled by default for stability)")
                    # Image extraction disabled - uncomment below if needed
                    # for img_index, img in enumerate(images):
                    #     try:
                    #         xref = img[0]
                    #         base_image = doc.extract_image(xref)
                    #         image_bytes = base_image["image"]
                    #         image_ext = base_image["ext"]
                    #
                    #         # Skip excessively large images to prevent memory issues
                    #         if len(image_bytes) > 50 * 1024 * 1024:  # 50MB limit per image
                    #             logger.warning(f"Image on page {page_num + 1} exceeds 50MB, skipping")
                    #             continue
                    #
                    #         res_id = f"img_p{page_num+1}_{img_index}_{xref}"
                    #         res = ImageResource(
                    #             id=res_id,
                    #             file_name=f"image_{page_num+1}_{img_index}.{image_ext}",
                    #             media_type=f"image/{image_ext}",
                    #             data=image_bytes,
                    #             width=base_image.get("width"),
                    #             height=base_image.get("height"),
                    #         )
                    #         book.resources[res_id] = res
                    #
                    #         # Add image block
                    #         chapter.blocks.append(
                    #             Block(
                    #                 chapter_id=chapter.id,
                    #                 type=BlockType.IMAGE,
                    #                 source_text="",
                    #                 order_index=block_counter,
                    #                 resource_id=res_id,
                    #                 is_translatable=False,
                    #             )
                    #         )
                    #         block_counter += 1
                    #     except Exception as e:
                    #         logger.warning(f"Failed to extract image {img_index} from page {page_num + 1}: {str(e)}")
                    #         continue
                except Exception as e:
                    logger.warning(f"Failed to check images on page {page_num + 1}: {str(e)}")

                if chapter.blocks:
                    book.chapters.append(chapter)

            logger.info(f"PDF parsed: {len(book.chapters)} pages/chapters, {book.total_blocks()} blocks.")
        finally:
            doc.close()

        return book
