"""Web-based main window for BookBridge."""

import logging
import sys
from pathlib import Path

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QMainWindow, QMessageBox

from bookbridge.ui.web_bridge import WebBridge

logger = logging.getLogger(__name__)

_JS_LEVELS = {
    "DebugMessageLevel": logging.DEBUG,
    "InfoMessageLevel": logging.INFO,
    "WarningMessageLevel": logging.WARNING,
    "ErrorMessageLevel": logging.ERROR,
}


class LoggingWebPage(QWebEnginePage):
    """QWebEnginePage that forwards the browser console into the app log."""

    def javaScriptConsoleMessage(self, level, message, line, source):  # noqa: ANN001
        level_name = getattr(level, "name", str(level))
        logger.log(
            _JS_LEVELS.get(level_name, logging.INFO),
            "UI JavaScript [%s] %s:%s: %s",
            level_name,
            source,
            line,
            message,
        )

    def javaScriptAlert(self, security_origin, msg):  # noqa: ANN001, N802
        logger.info("UI alert: %s", msg)

    def javaScriptError(self, message, line, source):  # noqa: ANN001, N802
        logger.error("UI JavaScript error %s:%s: %s", source, line, message)


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
        page = LoggingWebPage(self.web_view)
        self.web_view.setPage(page)
        self.web_bridge = WebBridge(self)
        self.web_channel = QWebChannel(page)
        self.web_channel.registerObject("bookBridge", self.web_bridge)
        page.setWebChannel(self.web_channel)
        self.setCentralWidget(self.web_view)

        self.web_view.loadFinished.connect(self._on_load_finished)
        page.renderProcessTerminated.connect(self._on_render_process_terminated)

        # Never let Qt destroy a QThread that is still running: that aborts the
        # process. If the user closes during a job, stop it and wait for the
        # worker to finish before actually closing the window.
        self._quit_when_idle = False
        self._close_poll = QTimer(self)
        self._close_poll.setInterval(250)
        self._close_poll.timeout.connect(self._finish_pending_close)

        html_path = self._locate_html()
        if html_path is None:
            logger.critical(
                "bookbridge.html was not found. Expected next to the package or in "
                "the working directory: %s",
                Path.cwd(),
            )
            self.web_view.setHtml(
                "<html><body style='font-family:sans-serif;padding:32px'>"
                "<h1>BookBridge UI is missing</h1>"
                "<p><b>bookbridge.html</b> could not be found. Reinstall BookBridge "
                "or check the application log for details.</p></body></html>"
            )
            return

        logger.info("Loading user interface from %s", html_path)
        self.web_view.setUrl(QUrl.fromLocalFile(str(html_path)))

    @staticmethod
    def _locate_html() -> Path | None:
        candidates = [Path(__file__).resolve().parents[2] / "bookbridge.html"]
        bundle_dir = getattr(sys, "_MEIPASS", None)
        if bundle_dir:
            candidates.append(Path(bundle_dir) / "bookbridge.html")
        candidates.append(Path.cwd() / "bookbridge.html")
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        return None

    def _on_load_finished(self, ok: bool) -> None:
        if ok:
            logger.info("User interface loaded successfully.")
        else:
            logger.error("User interface failed to load. Check the log for JavaScript errors.")

    def closeEvent(self, event) -> None:  # noqa: ANN001 - Qt signature
        labels = self.web_bridge.running_worker_labels()
        if not labels:
            self._close_poll.stop()
            self._quit_when_idle = False
            event.accept()
            return

        if self._quit_when_idle:
            # Already waiting for the worker to stop.
            event.ignore()
            return

        answer = QMessageBox.question(
            self,
            "BookBridge is still working",
            "A translation or book update is still running.\n\n"
            "Stop the background work and quit when it has finished?\n"
            "Translation progress is saved and can be resumed.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            event.ignore()
            return

        logger.info("Close requested; stopping background workers: %s", ", ".join(labels))
        self._quit_when_idle = True
        self.web_bridge.request_shutdown()
        self.setWindowTitle("BookBridge — stopping background work…")
        # Prevent a new job from sneaking in while we wait for the old worker
        # to stop (the close confirmation is no longer interactive).
        self.web_view.setEnabled(False)
        self.web_view.page().runJavaScript(
            "try{setStatusMsg('Stopping background work before closing…','warn')}catch(e){}"
        )
        self._close_poll.start()
        event.ignore()

    def _finish_pending_close(self) -> None:
        if not self._quit_when_idle:
            self._close_poll.stop()
            return
        if self.web_bridge.running_worker_labels():
            return
        self._close_poll.stop()
        self._quit_when_idle = False
        logger.info("Background workers stopped; closing the window.")
        self.close()

    def _on_render_process_terminated(self, status, exit_code: int) -> None:  # noqa: ANN001
        status_name = getattr(status, "name", str(status))
        logger.critical(
            "QtWebEngine render process terminated: status=%s exitCode=%s",
            status_name,
            exit_code,
        )
