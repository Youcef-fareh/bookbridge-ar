"""BookBridge Application Entry Point."""

import logging
import os
import sys

from PySide6.QtCore import Qt, QCoreApplication
from PySide6.QtWidgets import QApplication

from bookbridge.config.settings import settings
from bookbridge.logging_setup import log_environment, setup_logging

logger = logging.getLogger("bookbridge")


def main():
    # Logging must be configured first so that startup failures are recorded.
    setup_logging()
    log_environment()

    try:
        logger.info("Starting BookBridge v%s...", settings.version)

        # Ensure all directories exist BEFORE any components try to use them
        settings.ensure_directories()
        logger.info("Data directory ready: %s", settings.data_dir)

        # Configure QtWebEngine OpenGL context sharing
        QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
        os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.wayland=false")

        # Imported after logging is ready so their import-time logs land in the file.
        from bookbridge.database.migrations import run_migrations
        from bookbridge.ui.main_window import MainWindow

        # Apply database migrations
        run_migrations()
        logger.info("Database migrations are up to date.")

        # Launch PySide6 Application
        app = QApplication(sys.argv)
        app.setApplicationName("BookBridge")
        app.setOrganizationName("BookBridge")

        window = MainWindow()
        window.show()

        logger.info("Application window shown; entering event loop.")
        exit_code = app.exec()
        logger.info("Application exited with code %s.", exit_code)
        sys.exit(exit_code)
    except Exception:
        logger.critical("Fatal error during BookBridge startup.", exc_info=True)
        raise


if __name__ == "__main__":
    main()
