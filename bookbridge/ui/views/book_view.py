"""Book Library & Document Inspector View."""

from pathlib import Path
from typing import Callable, Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)
from bookbridge.database.repositories.book_repo import BookRepository
from bookbridge.documents.epub.parser import EpubParser
from bookbridge.documents.pdf.parser import PdfParser
from bookbridge.models.book import Book


class BookView(QWidget):
    def __init__(
        self,
        book_repo: BookRepository,
        on_start_translate: Callable[[Book], None],
    ):
        super().__init__()
        self.book_repo = book_repo
        self.on_start_translate = on_start_translate
        self.selected_book: Optional[Book] = None

        self.epub_parser = EpubParser()
        self.pdf_parser = PdfParser()

        self._setup_ui()
        self.refresh_books()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Header with Import Buttons
        header = QHBoxLayout()
        title = QLabel("Book Library & Inspector")
        title.setStyleSheet("font-size: 22px; font-weight: 800; color: #ffffff;")
        header.addWidget(title)
        header.addStretch()

        import_epub_btn = QPushButton("+ Import EPUB")
        import_epub_btn.setProperty("class", "PrimaryBtn")
        import_epub_btn.clicked.connect(self._on_import_epub)
        header.addWidget(import_epub_btn)

        import_pdf_btn = QPushButton("+ Import PDF")
        import_pdf_btn.setProperty("class", "SecondaryBtn")
        import_pdf_btn.clicked.connect(self._on_import_pdf)
        header.addWidget(import_pdf_btn)

        layout.addLayout(header)

        # Splitter: Books list on left, Chapter & Block inspector on right
        splitter = QSplitter(Qt.Horizontal)

        # Left Panel: Book List Card
        left_card = QFrame()
        left_card.setProperty("class", "Card")
        left_layout = QVBoxLayout(left_card)
        left_layout.setContentsMargins(12, 12, 12, 12)

        lbl_books = QLabel("Imported Books")
        lbl_books.setProperty("class", "CardTitle")
        left_layout.addWidget(lbl_books)

        self.books_table = QTableWidget()
        self.books_table.setColumnCount(3)
        self.books_table.setHorizontalHeaderLabels(["Title", "Format", "Author"])
        self.books_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.books_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.books_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.books_table.verticalHeader().setVisible(False)
        self.books_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.books_table.itemSelectionChanged.connect(self._on_book_selected)
        left_layout.addWidget(self.books_table)

        # Action buttons below book list
        book_action_layout = QHBoxLayout()
        self.translate_btn = QPushButton("Translate This Book")
        self.translate_btn.setProperty("class", "PrimaryBtn")
        self.translate_btn.setEnabled(False)
        self.translate_btn.clicked.connect(self._on_translate_clicked)
        book_action_layout.addWidget(self.translate_btn)

        self.delete_btn = QPushButton("Delete")
        self.delete_btn.setProperty("class", "DangerBtn")
        self.delete_btn.setEnabled(False)
        self.delete_btn.clicked.connect(self._on_delete_clicked)
        book_action_layout.addWidget(self.delete_btn)

        left_layout.addLayout(book_action_layout)
        splitter.addWidget(left_card)

        # Right Panel: Inspector Card (Chapters & Blocks)
        right_card = QFrame()
        right_card.setProperty("class", "Card")
        right_layout = QVBoxLayout(right_card)
        right_layout.setContentsMargins(12, 12, 12, 12)

        self.lbl_inspector = QLabel("Book Structure Inspector (Select a book)")
        self.lbl_inspector.setProperty("class", "CardTitle")
        right_layout.addWidget(self.lbl_inspector)

        self.tree_widget = QTreeWidget()
        self.tree_widget.setHeaderLabels(["Chapter / Element", "Type", "Text Preview"])
        self.tree_widget.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.tree_widget.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tree_widget.header().setSectionResizeMode(2, QHeaderView.Stretch)
        right_layout.addWidget(self.tree_widget)

        splitter.addWidget(right_card)
        splitter.setSizes([350, 650])
        layout.addWidget(splitter)

    def refresh_books(self):
        books = self.book_repo.list_books()
        self.books_table.setRowCount(len(books))
        self._books_cache = books
        for r_idx, b in enumerate(books):
            self.books_table.setItem(r_idx, 0, QTableWidgetItem(b.metadata.title))
            self.books_table.setItem(r_idx, 1, QTableWidgetItem(b.source_format.upper()))
            self.books_table.setItem(r_idx, 2, QTableWidgetItem(b.metadata.author))

    def _on_import_epub(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Import EPUB File", "", "EPUB Files (*.epub)"
        )
        if not file_path:
            return
        try:
            book = self.epub_parser.parse(Path(file_path))
            self.book_repo.save_book(book)
            self.refresh_books()
            QMessageBox.information(
                self,
                "Book Imported",
                f"Successfully parsed '{book.metadata.title}' with {len(book.chapters)} chapters and {book.total_translatable_blocks()} translatable blocks.",
            )
        except Exception as ex:
            QMessageBox.critical(self, "Import Failed", f"Failed to import EPUB:\n{str(ex)}")

    def _on_import_pdf(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Import PDF File", "", "PDF Files (*.pdf)"
        )
        if not file_path:
            return
        try:
            book = self.pdf_parser.parse(Path(file_path))
            self.book_repo.save_book(book)
            self.refresh_books()
            QMessageBox.information(
                self,
                "PDF Imported",
                f"Successfully parsed '{book.metadata.title}' with {len(book.chapters)} pages/chapters and {book.total_translatable_blocks()} blocks.",
            )
        except Exception as ex:
            import logging
            logger = logging.getLogger(__name__)
            logger.exception(f"PDF import error: {str(ex)}")
            QMessageBox.critical(
                self,
                "Import Failed",
                f"Failed to import PDF:\n\n{str(ex)}\n\nThe file may be corrupted, in an unsupported format, or too large to process.\nPlease check the application logs for details.",
            )

    def _on_book_selected(self):
        selected_rows = self.books_table.selectedItems()
        if not selected_rows:
            self.translate_btn.setEnabled(False)
            self.delete_btn.setEnabled(False)
            return

        row = self.books_table.currentRow()
        if 0 <= row < len(self._books_cache):
            book_meta = self._books_cache[row]
            # Load full book with chapters & blocks
            self.selected_book = self.book_repo.get_book(book_meta.id)
            self.translate_btn.setEnabled(True)
            self.delete_btn.setEnabled(True)
            self._render_inspector()

    def _render_inspector(self):
        self.tree_widget.clear()
        if not self.selected_book:
            return

        self.lbl_inspector.setText(f"Structure Inspector: {self.selected_book.metadata.title}")

        for ch in self.selected_book.chapters:
            ch_item = QTreeWidgetItem(self.tree_widget)
            ch_item.setText(0, ch.title)
            ch_item.setText(1, f"Chapter ({len(ch.blocks)} blocks)")
            ch_item.setText(2, "")

            for blk in ch.blocks[:25]:  # preview first 25 blocks
                blk_item = QTreeWidgetItem(ch_item)
                blk_item.setText(0, f"Block #{blk.order_index + 1}")
                blk_item.setText(1, blk.type.value.upper())
                preview = blk.translated_text or blk.source_text
                blk_item.setText(2, preview[:90] + ("..." if len(preview) > 90 else ""))

            if len(ch.blocks) > 25:
                more_item = QTreeWidgetItem(ch_item)
                more_item.setText(0, f"... and {len(ch.blocks) - 25} more blocks")

        self.tree_widget.expandToDepth(0)

    def _on_translate_clicked(self):
        if self.selected_book:
            self.on_start_translate(self.selected_book)

    def _on_delete_clicked(self):
        if not self.selected_book:
            return
        confirm = QMessageBox.question(
            self,
            "Delete Book",
            f"Are you sure you want to remove '{self.selected_book.metadata.title}' from the database?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if confirm == QMessageBox.Yes:
            self.book_repo.delete_book(self.selected_book.id)
            self.selected_book = None
            self.refresh_books()
            self.tree_widget.clear()
            self.translate_btn.setEnabled(False)
            self.delete_btn.setEnabled(False)
