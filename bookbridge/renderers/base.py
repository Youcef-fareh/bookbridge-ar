"""Base Document Renderer Abstract Interface."""

from abc import ABC, abstractmethod
from pathlib import Path
from bookbridge.models.book import Book


class DocumentRenderer(ABC):
    @abstractmethod
    def render(self, book: Book, output_path: Path) -> Path:
        """Render translated Universal Book Model to target format."""
        pass
