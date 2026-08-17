"""Base Document Parser Abstract Interface."""

from abc import ABC, abstractmethod
from pathlib import Path
from bookbridge.models.book import Book


class DocumentParser(ABC):
    @abstractmethod
    def parse(self, file_path: Path) -> Book:
        """Parse source document into Universal Book Model."""
        pass
