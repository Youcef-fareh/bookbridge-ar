"""EPUB Parser extracting Universal Book Model representation."""

import logging
from pathlib import Path
from bs4 import BeautifulSoup, NavigableString, Tag
import ebooklib
from ebooklib import epub
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


class EpubParser(DocumentParser):
    def parse(self, file_path: Path) -> Book:
        logger.info(f"Parsing EPUB file: {file_path}")
        book_epub = epub.read_epub(str(file_path))

        # Extract metadata
        title = "Untitled Book"
        titles = book_epub.get_metadata("DC", "title")
        if titles:
            title = titles[0][0]

        author = "Unknown Author"
        creators = book_epub.get_metadata("DC", "creator")
        if creators:
            author = creators[0][0]

        lang = "en"
        langs = book_epub.get_metadata("DC", "language")
        if langs:
            lang = langs[0][0]

        desc = ""
        descriptions = book_epub.get_metadata("DC", "description")
        if descriptions:
            desc = descriptions[0][0]

        publisher = ""
        publishers = book_epub.get_metadata("DC", "publisher")
        if publishers:
            publisher = publishers[0][0]

        identifier = ""
        identifiers = book_epub.get_metadata("DC", "identifier")
        if identifiers:
            identifier = identifiers[0][0]

        metadata = BookMetadata(
            title=title,
            author=author,
            language=lang,
            description=desc,
            publisher=publisher,
            identifier=identifier,
        )

        book = Book(
            metadata=metadata,
            source_format="epub",
            source_file_path=str(file_path),
        )

        # Extract Images and Resources
        for item in book_epub.get_items():
            if item.get_type() == ebooklib.ITEM_IMAGE:
                res_id = item.get_id()
                res = ImageResource(
                    id=res_id,
                    file_name=item.get_name(),
                    media_type=item.media_type,
                    data=item.get_content(),
                )
                book.resources[res_id] = res

            elif item.get_type() == ebooklib.ITEM_STYLE:
                css_content = item.get_content().decode("utf-8", errors="ignore")
                book.raw_styles_css[item.get_name()] = css_content

            elif item.get_type() == ebooklib.ITEM_COVER:
                metadata.cover_image_id = item.get_id()

        # Extract Chapters in Spine order
        spine_item_ids = [s[0] for s in book_epub.spine if isinstance(s, tuple) and s[0] != "nav"]
        chapter_order = 0

        for item in book_epub.get_items():
            if item.get_type() == ebooklib.ITEM_DOCUMENT:
                item_id = item.get_id()
                item_name = item.get_name().lower()
                # Skip nav/toc navigation documents
                if item_id.lower() in ("nav", "ncx", "toc") or item_name in ("nav.xhtml", "toc.xhtml", "nav.html", "toc.ncx"):
                    continue
                # Order by spine index if present
                order_index = spine_item_ids.index(item_id) if item_id in spine_item_ids else chapter_order
                chapter_order += 1

                content = item.get_content().decode("utf-8", errors="ignore")
                soup = BeautifulSoup(content, "html.parser")

                # Try to extract chapter title
                ch_title = f"Chapter {chapter_order}"
                h_tag = soup.find(["h1", "h2", "h3"])
                if h_tag and h_tag.get_text(strip=True):
                    ch_title = h_tag.get_text(strip=True)
                elif soup.title and soup.title.get_text(strip=True):
                    ch_title = soup.title.get_text(strip=True)

                chapter = Chapter(
                    book_id=book.id,
                    title=ch_title,
                    order_index=order_index,
                    source_file_path=item.get_name(),
                )

                # Extract Blocks
                body = soup.find("body") or soup
                block_order = 0

                for element in body.find_all(
                    ["h1", "h2", "h3", "h4", "h5", "h6", "p", "blockquote", "li", "img", "table", "hr"],
                    recursive=True,
                ):
                    # Avoid duplicate processing of nested elements (e.g. li inside ul or p inside blockquote)
                    if element.parent.name in ["blockquote", "li", "p", "td", "th"]:
                        continue

                    tag_name = element.name.lower()
                    text = element.get_text(strip=False).strip()
                    attrs = {k: str(v) for k, v in element.attrs.items()}

                    if tag_name in ["h1", "h2", "h3", "h4", "h5", "h6"]:
                        blk_type = BlockType.HEADING
                    elif tag_name == "blockquote":
                        blk_type = BlockType.QUOTE
                    elif tag_name == "li":
                        blk_type = BlockType.LIST
                    elif tag_name == "img":
                        blk_type = BlockType.IMAGE
                    elif tag_name == "table":
                        blk_type = BlockType.TABLE
                    elif tag_name == "hr":
                        blk_type = BlockType.PAGE_BREAK
                    else:
                        blk_type = BlockType.PARAGRAPH

                    # Image block
                    res_id = None
                    if blk_type == BlockType.IMAGE:
                        src = element.get("src", "")
                        # Match resource by filename
                        for r_id, r in book.resources.items():
                            if r.file_name.endswith(src) or src.endswith(r.file_name):
                                res_id = r_id
                                break

                    # Skip empty non-image blocks
                    if blk_type != BlockType.IMAGE and not text:
                        continue

                    block = Block(
                        chapter_id=chapter.id,
                        type=blk_type,
                        source_text=text,
                        order_index=block_order,
                        tag_attributes=attrs,
                        resource_id=res_id,
                        source_location=SourceLocation(
                            file_path=item.get_name(),
                            tag_name=tag_name,
                            line_number=getattr(element, "sourceline", None),
                        ),
                        is_translatable=(blk_type != BlockType.IMAGE and bool(text)),
                    )
                    chapter.blocks.append(block)
                    block_order += 1

                if chapter.blocks:
                    book.chapters.append(chapter)

        # Sort chapters by order_index
        book.chapters.sort(key=lambda c: c.order_index)
        logger.info(f"EPUB parsed successfully: {len(book.chapters)} chapters, {book.total_blocks()} blocks.")
        return book
