"""Web-based main window for BookBridge."""

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QMainWindow

from bookbridge.ui.web_bridge import WebBridge


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
        self.web_view = QWebEngineView(self)
        self.web_bridge = WebBridge(self)
        self.web_channel = QWebChannel(self.web_view.page())
        self.web_channel.registerObject("bookBridge", self.web_bridge)
        self.web_view.page().setWebChannel(self.web_channel)
        self.setCentralWidget(self.web_view)

        html_path = Path(__file__).resolve().parents[2] / "bookbridge.html"
        self.web_view.setUrl(QUrl.fromLocalFile(str(html_path)))

