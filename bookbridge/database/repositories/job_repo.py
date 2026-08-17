from datetime import datetime, timezone
import json
from typing import List, Optional
from bookbridge.database.connection import db
from bookbridge.models.job import TranslationJob, Segment
from bookbridge.config.constants import JobStatus, SegmentStatus, TranslationStyleType


def _to_iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def _from_iso(val: Optional[str]) -> Optional[datetime]:
    if not val:
        return None
    if isinstance(val, datetime):
        return val
    try:
        return datetime.fromisoformat(val)
    except Exception:
        return None


class JobRepository:
    def create_job(self, job: TranslationJob) -> None:
        with db.session() as conn:
            started_at_str = _to_iso(job.started_at)
            finished_at_str = _to_iso(job.finished_at)
            conn.execute(
                """
                INSERT INTO translation_jobs (
                    id, book_id, book_title, status, source_language, target_language,
                    style, glossary_profile_id, output_format, total_chapters, completed_chapters,
                    current_chapter_title, total_segments, completed_segments, cached_segments,
                    failed_segments, retried_segments, total_tokens_used, error_message,
                    started_at, finished_at, updated_at, custom_settings_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
                ON CONFLICT(id) DO UPDATE SET
                    book_id=excluded.book_id,
                    book_title=excluded.book_title,
                    status=excluded.status,
                    source_language=excluded.source_language,
                    target_language=excluded.target_language,
                    style=excluded.style,
                    glossary_profile_id=excluded.glossary_profile_id,
                    output_format=excluded.output_format,
                    total_chapters=excluded.total_chapters,
                    completed_chapters=excluded.completed_chapters,
                    current_chapter_title=excluded.current_chapter_title,
                    total_segments=excluded.total_segments,
                    completed_segments=excluded.completed_segments,
                    cached_segments=excluded.cached_segments,
                    failed_segments=excluded.failed_segments,
                    retried_segments=excluded.retried_segments,
                    total_tokens_used=excluded.total_tokens_used,
                    error_message=excluded.error_message,
                    started_at=excluded.started_at,
                    finished_at=excluded.finished_at,
                    updated_at=CURRENT_TIMESTAMP,
                    custom_settings_json=excluded.custom_settings_json;
                """,
                (
                    job.id,
                    job.book_id,
                    job.book_title,
                    job.status.value,
                    job.source_language,
                    job.target_language,
                    job.style.value,
                    job.glossary_profile_id,
                    job.output_format,
                    job.total_chapters,
                    job.completed_chapters,
                    job.current_chapter_title,
                    job.total_segments,
                    job.completed_segments,
                    job.cached_segments,
                    job.failed_segments,
                    job.retried_segments,
                    job.total_tokens_used,
                    job.error_message,
                    started_at_str,
                    finished_at_str,
                    json.dumps(job.custom_settings),
                ),
            )

    def update_job_status(
        self,
        job_id: str,
        status: JobStatus,
        error_message: Optional[str] = None,
        finished: bool = False,
    ) -> None:
        with db.session() as conn:
            finished_at_str = datetime.now(timezone.utc).isoformat() if finished else None
            conn.execute(
                """
                UPDATE translation_jobs SET
                    status = ?,
                    error_message = coalesce(?, error_message),
                    finished_at = coalesce(?, finished_at),
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?;
                """,
                (status.value, error_message, finished_at_str, job_id),
            )

    def update_job_progress(
        self,
        job_id: str,
        completed_segments: int,
        cached_segments: int,
        failed_segments: int,
        retried_segments: int,
        total_tokens_used: int,
        completed_chapters: int,
        current_chapter_title: str,
    ) -> None:
        with db.session() as conn:
            conn.execute(
                """
                UPDATE translation_jobs SET
                    completed_segments = ?,
                    cached_segments = ?,
                    failed_segments = ?,
                    retried_segments = ?,
                    total_tokens_used = ?,
                    completed_chapters = ?,
                    current_chapter_title = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?;
                """,
                (
                    completed_segments,
                    cached_segments,
                    failed_segments,
                    retried_segments,
                    total_tokens_used,
                    completed_chapters,
                    current_chapter_title,
                    job_id,
                ),
            )

    def get_job(self, job_id: str) -> Optional[TranslationJob]:
        conn = db.get_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM translation_jobs WHERE id = ?", (job_id,))
        row = c.fetchone()
        if not row:
            return None

        custom_settings = json.loads(row["custom_settings_json"]) if row["custom_settings_json"] else {}
        return TranslationJob(
            id=row["id"],
            book_id=row["book_id"],
            book_title=row["book_title"] or "",
            status=JobStatus(row["status"]),
            source_language=row["source_language"],
            target_language=row["target_language"],
            style=TranslationStyleType(row["style"]),
            glossary_profile_id=row["glossary_profile_id"],
            output_format=row["output_format"],
            total_chapters=row["total_chapters"],
            completed_chapters=row["completed_chapters"],
            current_chapter_title=row["current_chapter_title"] or "",
            total_segments=row["total_segments"],
            completed_segments=row["completed_segments"],
            cached_segments=row["cached_segments"],
            failed_segments=row["failed_segments"],
            retried_segments=row["retried_segments"],
            total_tokens_used=row["total_tokens_used"],
            error_message=row["error_message"],
            started_at=_from_iso(row["started_at"]),
            finished_at=_from_iso(row["finished_at"]),
            updated_at=_from_iso(row["updated_at"]) or datetime.utcnow(),
            custom_settings=custom_settings,
        )

    def list_jobs(self, limit: int = 50) -> List[TranslationJob]:
        conn = db.get_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM translation_jobs ORDER BY updated_at DESC LIMIT ?", (limit,))
        jobs = []
        for row in c.fetchall():
            custom_settings = json.loads(row["custom_settings_json"]) if row["custom_settings_json"] else {}
            jobs.append(
                TranslationJob(
                    id=row["id"],
                    book_id=row["book_id"],
                    book_title=row["book_title"] or "",
                    status=JobStatus(row["status"]),
                    source_language=row["source_language"],
                    target_language=row["target_language"],
                    style=TranslationStyleType(row["style"]),
                    glossary_profile_id=row["glossary_profile_id"],
                    output_format=row["output_format"],
                    total_chapters=row["total_chapters"],
                    completed_chapters=row["completed_chapters"],
                    current_chapter_title=row["current_chapter_title"] or "",
                    total_segments=row["total_segments"],
                    completed_segments=row["completed_segments"],
                    cached_segments=row["cached_segments"],
                    failed_segments=row["failed_segments"],
                    retried_segments=row["retried_segments"],
                    total_tokens_used=row["total_tokens_used"],
                    error_message=row["error_message"],
                    started_at=_from_iso(row["started_at"]),
                    finished_at=_from_iso(row["finished_at"]),
                    updated_at=_from_iso(row["updated_at"]) or datetime.utcnow(),
                    custom_settings=custom_settings,
                )
            )
        return jobs

    def save_segments(self, segments: List[Segment]) -> None:
        with db.session() as conn:
            for s in segments:
                conn.execute(
                    """
                    INSERT INTO segments (
                        id, job_id, chapter_id, block_ids_json, order_index, source_text,
                        translated_text, status, cache_key, source_hash, provider_used,
                        model_used, credential_id_used, tokens_used, retries_count,
                        error_message, validation_notes, translated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        translated_text=excluded.translated_text,
                        status=excluded.status,
                        cache_key=excluded.cache_key,
                        source_hash=excluded.source_hash,
                        provider_used=excluded.provider_used,
                        model_used=excluded.model_used,
                        credential_id_used=excluded.credential_id_used,
                        tokens_used=excluded.tokens_used,
                        retries_count=excluded.retries_count,
                        error_message=excluded.error_message,
                        validation_notes=excluded.validation_notes,
                        translated_at=excluded.translated_at;
                    """,
                    (
                        s.id,
                        s.job_id,
                        s.chapter_id,
                        json.dumps(s.block_ids),
                        s.order_index,
                        s.source_text,
                        s.translated_text,
                        s.status.value,
                        s.cache_key,
                        s.source_hash,
                        s.provider_used,
                        s.model_used,
                        s.credential_id_used,
                        s.tokens_used,
                        s.retries_count,
                        s.error_message,
                        s.validation_notes,
                        _to_iso(s.translated_at),
                    ),
                )

    def update_segment(self, segment: Segment) -> None:
        with db.session() as conn:
            conn.execute(
                """
                UPDATE segments SET
                    translated_text = ?,
                    status = ?,
                    cache_key = ?,
                    source_hash = ?,
                    provider_used = ?,
                    model_used = ?,
                    credential_id_used = ?,
                    tokens_used = ?,
                    retries_count = ?,
                    error_message = ?,
                    validation_notes = ?,
                    translated_at = ?
                WHERE id = ?;
                """,
                (
                    segment.translated_text,
                    segment.status.value,
                    segment.cache_key,
                    segment.source_hash,
                    segment.provider_used,
                    segment.model_used,
                    segment.credential_id_used,
                    segment.tokens_used,
                    segment.retries_count,
                    segment.error_message,
                    segment.validation_notes,
                    _to_iso(segment.translated_at),
                    segment.id,
                ),
            )

    def get_job_segments(self, job_id: str) -> List[Segment]:
        conn = db.get_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM segments WHERE job_id = ? ORDER BY order_index ASC", (job_id,))
        segments = []
        for row in c.fetchall():
            block_ids = json.loads(row["block_ids_json"]) if row["block_ids_json"] else []
            segments.append(
                Segment(
                    id=row["id"],
                    job_id=row["job_id"],
                    chapter_id=row["chapter_id"],
                    block_ids=block_ids,
                    order_index=row["order_index"],
                    source_text=row["source_text"],
                    translated_text=row["translated_text"],
                    status=SegmentStatus(row["status"]),
                    cache_key=row["cache_key"],
                    source_hash=row["source_hash"],
                    provider_used=row["provider_used"],
                    model_used=row["model_used"],
                    credential_id_used=row["credential_id_used"],
                    tokens_used=row["tokens_used"],
                    retries_count=row["retries_count"],
                    error_message=row["error_message"],
                    validation_notes=row["validation_notes"],
                    translated_at=row["translated_at"],
                )
            )
        return segments

    def get_pending_segments(self, job_id: str) -> List[Segment]:
        all_segs = self.get_job_segments(job_id)
        return [
            s
            for s in all_segs
            if s.status in (SegmentStatus.PENDING, SegmentStatus.FAILED, SegmentStatus.NEEDS_REVIEW)
        ]
