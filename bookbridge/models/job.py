"""Translation job, segment, and result models."""

from datetime import datetime, timezone
import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from bookbridge.config.constants import JobStatus, SegmentStatus, TranslationStyleType


class TranslationJob(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    book_id: str
    book_title: str = ""
    status: JobStatus = JobStatus.QUEUED
    source_language: str = "en"
    target_language: str = "ar"
    style: TranslationStyleType = TranslationStyleType.NATURAL
    glossary_profile_id: Optional[str] = None
    output_format: str = "epub"
    total_chapters: int = 0
    completed_chapters: int = 0
    current_chapter_title: str = ""
    total_segments: int = 0
    completed_segments: int = 0
    cached_segments: int = 0
    failed_segments: int = 0
    retried_segments: int = 0
    total_tokens_used: int = 0
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    custom_settings: Dict[str, Any] = Field(default_factory=dict)

    @property
    def progress_percent(self) -> float:
        if self.total_segments == 0:
            return 0.0
        return min(100.0, (self.completed_segments / self.total_segments) * 100.0)


class Segment(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    job_id: str
    chapter_id: str
    block_ids: List[str] = Field(default_factory=list)
    order_index: int = 0
    source_text: str
    translated_text: Optional[str] = None
    status: SegmentStatus = SegmentStatus.PENDING
    cache_key: Optional[str] = None
    source_hash: Optional[str] = None
    provider_used: Optional[str] = None
    model_used: Optional[str] = None
    credential_id_used: Optional[str] = None
    tokens_used: int = 0
    retries_count: int = 0
    error_message: Optional[str] = None
    validation_notes: Optional[str] = None
    translated_at: Optional[datetime] = None


class TranslationResult(BaseModel):
    success: bool
    translated_text: str = ""
    source_text: str = ""
    provider: str = ""
    model: str = ""
    credential_id: str = ""
    tokens_used: int = 0
    cached: bool = False
    error: Optional[str] = None
    retryable: bool = False
    validation_errors: List[str] = Field(default_factory=list)
    raw_response: Optional[str] = None
