"""Master MainWindow for BookBridge AI Book Translation Desktop Application."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from bookbridge.database.repositories.book_repo import BookRepository
from bookbridge.database.repositories.credential_repo import CredentialRepository
from bookbridge.database.repositories.glossary_repo import GlossaryRepository
from bookbridge.database.repositories.job_repo import JobRepository
from bookbridge.models.book import Book
from bookbridge.ui.theme import DARK_THEME_QSS
from bookbridge.ui.views.book_view import BookView
from bookbridge.ui.views.credentials_view import CredentialsView
from bookbridge.ui.views.dashboard_view import DashboardView
from bookbridge.ui.views.glossary_view import GlossaryView
from bookbridge.ui.views.settings_view import SettingsView
from bookbridge.ui.views.translate_view import TranslateView


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("BookBridge — AI Book Translation")
        # Set window size safely to avoid Wayland buffer issues
        screen = self.screen()
        if screen:
            available_geometry = screen.availableGeometry()
            # Calculate safe size (use 90% of available screen width/height, but don't exceed)
            safe_width = min(1200, int(available_geometry.width() * 0.9))
            safe_height = min(780, int(available_geometry.height() * 0.9))
            self.resize(safe_width, safe_height)
        else:
            self.resize(1200, 780)
        self.setStyleSheet(DARK_THEME_QSS)

        # Repositories
        self.book_repo = BookRepository()
        self.job_repo = JobRepository()
        self.cred_repo = CredentialRepository()
        self.glossary_repo = GlossaryRepository()

        self._setup_ui()

    def _setup_ui(self):
        central = QWidget()
        central.setObjectName("CentralWidget")
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Sidebar Frame
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 16)
        sidebar_layout.setSpacing(4)

        # Logo / Title
        lbl_title = QLabel("BookBridge")
        lbl_title.setObjectName("AppTitle")
        lbl_sub = QLabel("AI BOOK TRANSLATOR")
        lbl_sub.setObjectName("AppSubtitle")
        sidebar_layout.addWidget(lbl_title)
        sidebar_layout.addWidget(lbl_sub)

        # Navigation Buttons
        self.nav_buttons = {}
        nav_items = [
            ("dashboard", "📊  Dashboard"),
            ("books", "📚  Book Library"),
            ("translate", "🌐  Translation Studio"),
            ("glossary", "📖  Glossary & Terms"),
            ("keys", "🔑  API Credentials"),
            ("settings", "⚙️  Settings"),
        ]

        for key, text in nav_items:
            btn = QPushButton(text)
            btn.setProperty("class", "NavBtn")
            btn.setCheckable(True)
            btn.clicked.connect(lambda _, k=key: self.navigate_to(k))
            sidebar_layout.addWidget(btn)
            self.nav_buttons[key] = btn

        sidebar_layout.addStretch()

        # Version tag
        lbl_ver = QLabel("v1.0.0 — Local First")
        lbl_ver.setStyleSheet("color: #cbd5e1; font-size: 11px; padding: 0 16px;")
        sidebar_layout.addWidget(lbl_ver)

        main_layout.addWidget(sidebar)

        # Stacked Views Container
        self.stack = QStackedWidget()

        # Initialize Views
        self.view_dashboard = DashboardView(
            self.book_repo, self.job_repo, self.cred_repo, self.navigate_to
        )
        self.view_books = BookView(self.book_repo, self._on_start_translate_book)
        self.view_translate = TranslateView(self.book_repo, self.job_repo, self.glossary_repo)
        self.view_glossary = GlossaryView(self.glossary_repo)
        self.view_credentials = CredentialsView(self.cred_repo)
        self.view_settings = SettingsView()

        self.views_map = {
            "dashboard": self.view_dashboard,
            "books": self.view_books,
            "translate": self.view_translate,
            "glossary": self.view_glossary,
            "keys": self.view_credentials,
            "settings": self.view_settings,
        }

        for view in self.views_map.values():
            self.stack.addWidget(view)

        main_layout.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        # Navigate to Dashboard initially
        self.navigate_to("dashboard")

    def navigate_to(self, view_key: str):
        if view_key in self.views_map:
            target_widget = self.views_map[view_key]
            self.stack.setCurrentWidget(target_widget)

            # Update button check states
            for k, btn in self.nav_buttons.items():
                btn.setChecked(k == view_key)

            # Refresh view data when navigating to it
            if hasattr(target_widget, "refresh_data"):
                target_widget.refresh_data()
            elif hasattr(target_widget, "refresh_books"):
                target_widget.refresh_books()
            elif hasattr(target_widget, "load_books_and_glossaries"):
                target_widget.load_books_and_glossaries()
            elif hasattr(target_widget, "refresh_credentials"):
                target_widget.refresh_credentials()
            elif hasattr(target_widget, "refresh_profiles"):
                target_widget.refresh_profiles()

    def _on_start_translate_book(self, book: Book):
        self.view_translate.set_active_book(book)
        self.navigate_to("translate")
