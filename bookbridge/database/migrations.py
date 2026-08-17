"""Database Migration Runner."""

import logging
from bookbridge.database.connection import db
from bookbridge.database.schema import SCHEMA_V1

logger = logging.getLogger(__name__)

CURRENT_VERSION = 1


def run_migrations() -> None:
    """Run pending database schema migrations."""
    with db.session() as conn:
        # Create migrations table if not exists
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);"
        )
        cursor = conn.execute("SELECT MAX(version) FROM schema_migrations;")
        row = cursor.fetchone()
        latest_version = row[0] if row and row[0] is not None else 0

        if latest_version < 1:
            logger.info("Applying Database Migration V1...")
            conn.executescript(SCHEMA_V1)
            conn.execute("INSERT INTO schema_migrations (version) VALUES (1);")
            logger.info("Database Migration V1 applied successfully.")
