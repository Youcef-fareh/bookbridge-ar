"""Translation Memory and Request Cache Repository."""

import hashlib
import uuid
from typing import Optional
from bookbridge.database.connection import db


class MemoryRepository:
    def get_cache_entry(self, cache_key: str) -> Optional[str]:
        conn = db.get_connection()
        c = conn.cursor()
        c.execute("SELECT translated_text FROM translation_cache WHERE cache_key = ?", (cache_key,))
        row = c.fetchone()
        return row["translated_text"] if row else None

    def save_cache_entry(
        self,
        cache_key: str,
        translated_text: str,
        provider: str = "",
        model: str = "",
        tokens_used: int = 0,
    ) -> None:
        with db.session() as conn:
            conn.execute(
                """
                INSERT INTO translation_cache (cache_key, translated_text, provider, model, tokens_used, created_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(cache_key) DO UPDATE SET
                    translated_text=excluded.translated_text,
                    provider=excluded.provider,
                    model=excluded.model,
                    tokens_used=excluded.tokens_used;
                """,
                (cache_key, translated_text, provider, model, tokens_used),
            )

    def find_tm_match(
        self, source_text: str, source_lang: str = "en", target_lang: str = "ar"
    ) -> Optional[str]:
        source_hash = hashlib.sha256(source_text.strip().encode("utf-8")).hexdigest()
        conn = db.get_connection()
        c = conn.cursor()
        c.execute(
            """
            SELECT translated_text FROM translation_memory
            WHERE source_hash = ? AND source_language = ? AND target_language = ?
            ORDER BY created_at DESC LIMIT 1;
            """,
            (source_hash, source_lang, target_lang),
        )
        row = c.fetchone()
        return row["translated_text"] if row else None

    def save_tm_entry(
        self,
        source_text: str,
        translated_text: str,
        source_lang: str = "en",
        target_lang: str = "ar",
        glossary_version: int = 1,
        style_type: str = "natural",
        provider: str = "",
        model: str = "",
    ) -> None:
        source_hash = hashlib.sha256(source_text.strip().encode("utf-8")).hexdigest()
        tm_id = str(uuid.uuid4())
        with db.session() as conn:
            conn.execute(
                """
                INSERT INTO translation_memory (
                    id, source_hash, source_text, translated_text, source_language,
                    target_language, glossary_version, style_type, provider, model, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP);
                """,
                (
                    tm_id,
                    source_hash,
                    source_text,
                    translated_text,
                    source_lang,
                    target_lang,
                    glossary_version,
                    style_type,
                    provider,
                    model,
                ),
            )
