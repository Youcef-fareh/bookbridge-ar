"""SQLite Connection Manager with WAL mode and thread safety."""

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional
from bookbridge.config.settings import settings


class DatabaseManager:
    _local = threading.local()

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or settings.db_path
        self._lock = threading.Lock()

    def get_connection(self) -> sqlite3.Connection:
        """Get or create a thread-local SQLite connection."""
        if not hasattr(self._local, "connection") or self._local.connection is None:
            settings.ensure_directories()
            conn = sqlite3.connect(
                str(self.db_path),
                timeout=30.0,
                check_same_thread=False,
            )
            # Enable WAL mode for high concurrency
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.execute("PRAGMA synchronous = NORMAL;")
            conn.execute("PRAGMA busy_timeout = 30000;")
            conn.row_factory = sqlite3.Row
            self._local.connection = conn
        return self._local.connection

    @contextmanager
    def session(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager for atomic transactions."""
        conn = self.get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def close(self) -> None:
        if hasattr(self._local, "connection") and self._local.connection is not None:
            try:
                self._local.connection.close()
            except Exception:
                pass
            self._local.connection = None


# Global database manager
db = DatabaseManager()
