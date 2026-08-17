"""BookBridge Application Entry Point."""

import logging
import sys
import os
from PySide6.QtWidgets import QApplication
from bookbridge.config.settings import settings
from bookbridge.database.migrations import run_migrations
from bookbridge.ui.main_window import MainWindow

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("bookbridge")


def main():
    logger.info(f"Starting BookBridge v{settings.version}...")
    
    # Ensure all directories exist BEFORE any components try to use them
    settings.ensure_directories()
    logger.info(f"Data directory: {settings.data_dir}")

    # Configure Qt to be more robust with display servers
    # Increase buffer and event handling timeouts to prevent Wayland crashes during PDF parsing
    os.environ.setdefault("QT_QPA_EGLFS_ALWAYS_OPENGL", "1")
    os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.wayland=false")

    # Apply database migrations
    run_migrations()

    # Launch PySide6 Application
    app = QApplication(sys.argv)
    app.setApplicationName("BookBridge")
    app.setOrganizationName("BookBridge")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
