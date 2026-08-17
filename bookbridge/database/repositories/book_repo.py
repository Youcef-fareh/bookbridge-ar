"""Book and Chapter Repository for SQLite persistence."""

import json
from typing import List, Optional
from bookbridge.database.connection import db
from bookbridge.models.book import Book, BookMetadata, Chapter, Block, ImageResource, SourceLocation
from bookbridge.config.constants import BlockType


class BookRepository:
    def save_book(self, book: Book) -> None:
        with db.session() as conn:
            # Save or update book
            metadata_json = json.dumps(book.metadata.extra)
            conn.execute(
                """
                INSERT INTO books (
                    id, title, author, language, publisher, identifier, description,
                    source_format, source_file_path, cover_image_id, metadata_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    title=excluded.title,
                    author=excluded.author,
                    language=excluded.language,
                    publisher=excluded.publisher,
                    identifier=excluded.identifier,
                    description=excluded.description,
                    source_format=excluded.source_format,
                    source_file_path=excluded.source_file_path,
                    cover_image_id=excluded.cover_image_id,
                    metadata_json=excluded.metadata_json,
                    updated_at=CURRENT_TIMESTAMP;
                """,
                (
                    book.id,
                    book.metadata.title,
                    book.metadata.author,
                    book.metadata.language,
                    book.metadata.publisher,
                    book.metadata.identifier,
                    book.metadata.description,
                    book.source_format,
                    book.source_file_path,
                    book.metadata.cover_image_id,
                    metadata_json,
                ),
            )

            # Save resources
            for res_id, res in book.resources.items():
                conn.execute(
                    """
                    INSERT INTO resources (id, book_id, file_name, media_type, relative_path, data, width, height)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        file_name=excluded.file_name,
                        media_type=excluded.media_type,
                        relative_path=excluded.relative_path,
                        data=excluded.data,
                        width=excluded.width,
                        height=excluded.height;
                    """,
                    (
                        res.id,
                        book.id,
                        res.file_name,
                        res.media_type,
                        res.relative_path,
                        res.data,
                        res.width,
                        res.height,
                    ),
                )

            # Save chapters and blocks
            for ch in book.chapters:
                ch_meta = json.dumps(ch.metadata)
                conn.execute(
                    """
                    INSERT INTO chapters (id, book_id, title, order_index, source_file_path, metadata_json)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        title=excluded.title,
                        order_index=excluded.order_index,
                        source_file_path=excluded.source_file_path,
                        metadata_json=excluded.metadata_json;
                    """,
                    (ch.id, book.id, ch.title, ch.order_index, ch.source_file_path, ch_meta),
                )

                for blk in ch.blocks:
                    style_json = json.dumps(blk.style)
                    source_loc_json = blk.source_location.model_dump_json() if blk.source_location else None
                    tag_attrs_json = json.dumps(blk.tag_attributes)
                    conn.execute(
                        """
                        INSERT INTO blocks (
                            id, chapter_id, type, source_text, translated_text, order_index,
                            is_translatable, style_json, source_location_json, resource_id, tag_attributes_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(id) DO UPDATE SET
                            type=excluded.type,
                            source_text=excluded.source_text,
                            translated_text=excluded.translated_text,
                            order_index=excluded.order_index,
                            is_translatable=excluded.is_translatable,
                            style_json=excluded.style_json,
                            source_location_json=excluded.source_location_json,
                            resource_id=excluded.resource_id,
                            tag_attributes_json=excluded.tag_attributes_json;
                        """,
                        (
                            blk.id,
                            ch.id,
                            blk.type.value,
                            blk.source_text,
                            blk.translated_text,
                            blk.order_index,
                            1 if blk.is_translatable else 0,
                            style_json,
                            source_loc_json,
                            blk.resource_id,
                            tag_attrs_json,
                        ),
                    )

    def get_book(self, book_id: str, load_data: bool = True) -> Optional[Book]:
        conn = db.get_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM books WHERE id = ?", (book_id,))
        row = c.fetchone()
        if not row:
            return None

        extra = json.loads(row["metadata_json"]) if row["metadata_json"] else {}
        metadata = BookMetadata(
            title=row["title"],
            author=row["author"] or "Unknown",
            language=row["language"] or "en",
            publisher=row["publisher"],
            identifier=row["identifier"],
            description=row["description"],
            cover_image_id=row["cover_image_id"],
            extra=extra,
        )

        book = Book(
            id=row["id"],
            metadata=metadata,
            source_format=row["source_format"],
            source_file_path=row["source_file_path"],
        )

        if not load_data:
            return book

        # Load resources
        c.execute("SELECT * FROM resources WHERE book_id = ?", (book_id,))
        for res_row in c.fetchall():
            res = ImageResource(
                id=res_row["id"],
                file_name=res_row["file_name"],
                media_type=res_row["media_type"],
                relative_path=res_row["relative_path"],
                data=res_row["data"],
                width=res_row["width"],
                height=res_row["height"],
            )
            book.resources[res.id] = res

        # Load chapters
        c.execute("SELECT * FROM chapters WHERE book_id = ? ORDER BY order_index ASC", (book_id,))
        chapter_rows = c.fetchall()
        for ch_row in chapter_rows:
            ch_meta = json.loads(ch_row["metadata_json"]) if ch_row["metadata_json"] else {}
            chapter = Chapter(
                id=ch_row["id"],
                book_id=book_id,
                title=ch_row["title"],
                order_index=ch_row["order_index"],
                source_file_path=ch_row["source_file_path"],
                metadata=ch_meta,
            )

            # Load blocks
            c.execute("SELECT * FROM blocks WHERE chapter_id = ? ORDER BY order_index ASC", (chapter.id,))
            for blk_row in c.fetchall():
                style = json.loads(blk_row["style_json"]) if blk_row["style_json"] else {}
                src_loc = (
                    SourceLocation.model_validate_json(blk_row["source_location_json"])
                    if blk_row["source_location_json"]
                    else None
                )
                tag_attrs = json.loads(blk_row["tag_attributes_json"]) if blk_row["tag_attributes_json"] else {}
                blk = Block(
                    id=blk_row["id"],
                    chapter_id=chapter.id,
                    type=BlockType(blk_row["type"]),
                    source_text=blk_row["source_text"],
                    translated_text=blk_row["translated_text"],
                    order_index=blk_row["order_index"],
                    is_translatable=bool(blk_row["is_translatable"]),
                    style=style,
                    source_location=src_loc,
                    resource_id=blk_row["resource_id"],
                    tag_attributes=tag_attrs,
                )
                chapter.blocks.append(blk)

            book.chapters.append(chapter)

        return book

    def list_books(self) -> List[Book]:
        conn = db.get_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM books ORDER BY updated_at DESC")
        books = []
        for row in c.fetchall():
            extra = json.loads(row["metadata_json"]) if row["metadata_json"] else {}
            metadata = BookMetadata(
                title=row["title"],
                author=row["author"] or "Unknown",
                language=row["language"] or "en",
                publisher=row["publisher"],
                identifier=row["identifier"],
                description=row["description"],
                cover_image_id=row["cover_image_id"],
                extra=extra,
            )
            books.append(
                Book(
                    id=row["id"],
                    metadata=metadata,
                    source_format=row["source_format"],
                    source_file_path=row["source_file_path"],
                )
            )
        return books

    def update_block_translation(self, block_id: str, translated_text: str) -> None:
        with db.session() as conn:
            conn.execute(
                "UPDATE blocks SET translated_text = ? WHERE id = ?",
                (translated_text, block_id),
            )

    def delete_book(self, book_id: str) -> None:
        with db.session() as conn:
            conn.execute("DELETE FROM books WHERE id = ?", (book_id,))
