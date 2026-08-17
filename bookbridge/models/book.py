"""Universal Book Model (UBM) - Document-agnostic book representation."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
import uuid
from bookbridge.config.constants import BlockType


class BookMetadata(BaseModel):
    title: str = "Untitled Book"
    author: str = "Unknown Author"
    language: str = "en"
    publisher: Optional[str] = None
    identifier: Optional[str] = None
    description: Optional[str] = None
    cover_image_id: Optional[str] = None
    extra: Dict[str, Any] = Field(default_factory=dict)


class ImageResource(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    media_type: str = "image/jpeg"
    file_name: str
    data: Optional[bytes] = None  # In-memory or loaded on demand
    relative_path: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None


class SourceLocation(BaseModel):
    file_path: Optional[str] = None
    tag_name: Optional[str] = None
    page_number: Optional[int] = None
    line_number: Optional[int] = None
    xpath: Optional[str] = None
    bbox: Optional[List[float]] = None  # [x0, y0, x1, y1] for PDF


class Block(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    chapter_id: str
    type: BlockType = BlockType.PARAGRAPH
    source_text: str = ""
    translated_text: Optional[str] = None
    order_index: int = 0
    style: Dict[str, Any] = Field(default_factory=dict)
    source_location: Optional[SourceLocation] = None
    resource_id: Optional[str] = None  # If image/resource block
    tag_attributes: Dict[str, str] = Field(default_factory=dict)
    is_translatable: bool = True

    @property
    def has_translatable_text(self) -> bool:
        return self.is_translatable and bool(self.source_text.strip()) and self.type != BlockType.IMAGE


class Chapter(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    book_id: str
    title: str = "Untitled Chapter"
    order_index: int = 0
    source_file_path: Optional[str] = None
    blocks: List[Block] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def translatable_blocks(self) -> List[Block]:
        return [b for b in self.blocks if b.has_translatable_text]


class Book(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    metadata: BookMetadata = Field(default_factory=BookMetadata)
    source_format: str = "epub"  # 'epub' | 'pdf'
    source_file_path: str = ""
    chapters: List[Chapter] = Field(default_factory=list)
    resources: Dict[str, ImageResource] = Field(default_factory=dict)
    raw_styles_css: Dict[str, str] = Field(default_factory=dict)  # filename -> css content

    def total_blocks(self) -> int:
        return sum(len(c.blocks) for c in self.chapters)

    def total_translatable_blocks(self) -> int:
        return sum(len(c.translatable_blocks()) for c in self.chapters)

    def get_chapter(self, chapter_id: str) -> Optional[Chapter]:
        for c in self.chapters:
            if c.id == chapter_id:
                return c
        return None
