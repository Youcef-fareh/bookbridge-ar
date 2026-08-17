"""Dashboard View displaying statistics, recent jobs, and system health."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from bookbridge.database.repositories.book_repo import BookRepository
from bookbridge.database.repositories.credential_repo import CredentialRepository
from bookbridge.database.repositories.job_repo import JobRepository


class DashboardView(QWidget):
    def __init__(
        self,
        book_repo: BookRepository,
        job_repo: JobRepository,
        cred_repo: CredentialRepository,
        on_navigate: callable,
    ):
        super().__init__()
        self.book_repo = book_repo
        self.job_repo = job_repo
        self.cred_repo = cred_repo
        self.on_navigate = on_navigate

        self._setup_ui()
        self.refresh_data()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)

        # Header
        header_layout = QHBoxLayout()
        title_label = QLabel("Dashboard & Overview")
        title_label.setStyleSheet("font-size: 22px; font-weight: 800; color: #ffffff;")
        header_layout.addWidget(title_label)
        header_layout.addStretch()

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setProperty("class", "SecondaryBtn")
        refresh_btn.clicked.connect(self.refresh_data)
        header_layout.addWidget(refresh_btn)

        layout.addLayout(header_layout)

        # Stat Cards Grid
        grid = QGridLayout()
        grid.setSpacing(16)

        # Books count card
        self.books_card = self._create_stat_card("Total Books", "0", "Imported library")
        grid.addWidget(self.books_card, 0, 0)

        # Jobs count card
        self.jobs_card = self._create_stat_card("Active / Total Jobs", "0 / 0", "Translation queue")
        grid.addWidget(self.jobs_card, 0, 1)

        # Tokens card
        self.tokens_card = self._create_stat_card("Tokens Processed", "0", "Total AI tokens")
        grid.addWidget(self.tokens_card, 0, 2)

        # API Keys card
        self.api_card = self._create_stat_card("Active API Keys", "0", "Healthy credentials")
        grid.addWidget(self.api_card, 0, 3)

        layout.addLayout(grid)

        # Action bar
        actions_frame = QFrame()
        actions_frame.setProperty("class", "Card")
        actions_layout = QHBoxLayout(actions_frame)
        actions_layout.setContentsMargins(16, 12, 16, 12)

        action_label = QLabel("Quick Actions:")
        action_label.setStyleSheet("font-weight: 700; color: #f8fafc;")
        actions_layout.addWidget(action_label)

        import_btn = QPushButton("+ Import EPUB / PDF")
        import_btn.setProperty("class", "PrimaryBtn")
        import_btn.clicked.connect(lambda: self.on_navigate("books"))
        actions_layout.addWidget(import_btn)

        keys_btn = QPushButton("Manage API Keys")
        keys_btn.setProperty("class", "SecondaryBtn")
        keys_btn.clicked.connect(lambda: self.on_navigate("keys"))
        actions_layout.addWidget(keys_btn)

        glossary_btn = QPushButton("Glossary & Terms")
        glossary_btn.setProperty("class", "SecondaryBtn")
        glossary_btn.clicked.connect(lambda: self.on_navigate("glossary"))
        actions_layout.addWidget(glossary_btn)

        actions_layout.addStretch()
        layout.addWidget(actions_frame)

        # Recent Translation Jobs Table
        table_frame = QFrame()
        table_frame.setProperty("class", "Card")
        table_layout = QVBoxLayout(table_frame)

        table_title = QLabel("Recent Translation Jobs")
        table_title.setProperty("class", "CardTitle")
        table_layout.addWidget(table_title)

        self.jobs_table = QTableWidget()
        self.jobs_table.setColumnCount(6)
        self.jobs_table.setHorizontalHeaderLabels([
            "Book Title", "Status", "Progress", "Segments", "Tokens", "Updated At"
        ])
        self.jobs_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.jobs_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.jobs_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.jobs_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.jobs_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.jobs_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.jobs_table.verticalHeader().setVisible(False)
        table_layout.addWidget(self.jobs_table)

        layout.addWidget(table_frame)

    def _create_stat_card(self, title: str, value: str, subtext: str) -> QFrame:
        card = QFrame()
        card.setProperty("class", "StatCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 12, 12, 12)
        card_layout.setSpacing(4)

        lbl_title = QLabel(title)
        lbl_title.setProperty("class", "StatLabel")
        card_layout.addWidget(lbl_title)

        lbl_val = QLabel(value)
        lbl_val.setProperty("class", "StatValue")
        lbl_val.setObjectName("ValLabel")
        card_layout.addWidget(lbl_val)

        lbl_sub = QLabel(subtext)
        lbl_sub.setStyleSheet("font-size: 11px; color: #64748b;")
        card_layout.addWidget(lbl_sub)

        return card

    def refresh_data(self):
        books = self.book_repo.list_books()
        jobs = self.job_repo.list_jobs(limit=15)
        creds = self.cred_repo.list_credentials(only_enabled=True)

        active_jobs = sum(1 for j in jobs if j.status.value == "running")
        total_tokens = sum(j.total_tokens_used for j in jobs)

        self.books_card.findChild(QLabel, "ValLabel").setText(str(len(books)))
        self.jobs_card.findChild(QLabel, "ValLabel").setText(f"{active_jobs} / {len(jobs)}")
        self.tokens_card.findChild(QLabel, "ValLabel").setText(f"{total_tokens:,}")
        self.api_card.findChild(QLabel, "ValLabel").setText(str(len(creds)))

        # Fill table
        self.jobs_table.setRowCount(len(jobs))
        for row_idx, job in enumerate(jobs):
            self.jobs_table.setItem(row_idx, 0, QTableWidgetItem(job.book_title or "Untitled"))
            
            status_item = QTableWidgetItem(job.status.value.upper())
            self.jobs_table.setItem(row_idx, 1, status_item)

            progress_str = f"{job.progress_percent:.1f}%"
            self.jobs_table.setItem(row_idx, 2, QTableWidgetItem(progress_str))

            segments_str = f"{job.completed_segments} / {job.total_segments}"
            self.jobs_table.setItem(row_idx, 3, QTableWidgetItem(segments_str))

            self.jobs_table.setItem(row_idx, 4, QTableWidgetItem(f"{job.total_tokens_used:,}"))

            time_str = job.updated_at.strftime("%Y-%m-%d %H:%M") if hasattr(job.updated_at, "strftime") else str(job.updated_at)[:16]
            self.jobs_table.setItem(row_idx, 5, QTableWidgetItem(time_str))
