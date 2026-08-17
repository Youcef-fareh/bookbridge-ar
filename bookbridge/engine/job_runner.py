"""Async Job Runner for Book Translation with Pause, Resume, and Event Hooks."""

import asyncio
from datetime import datetime, timezone
import logging
from typing import Callable, Optional
from bookbridge.config.constants import JobStatus, SegmentStatus
from bookbridge.database.repositories.book_repo import BookRepository
from bookbridge.database.repositories.glossary_repo import GlossaryRepository
from bookbridge.database.repositories.job_repo import JobRepository
from bookbridge.engine.translator import TranslationPipeline
from bookbridge.models.glossary import GlossaryProfile
from bookbridge.models.job import TranslationJob, Segment
from bookbridge.segmentation.engine import SegmentationEngine

logger = logging.getLogger(__name__)


class JobRunner:
    def __init__(
        self,
        job_repo: Optional[JobRepository] = None,
        book_repo: Optional[BookRepository] = None,
        glossary_repo: Optional[GlossaryRepository] = None,
        pipeline: Optional[TranslationPipeline] = None,
    ):
        self.job_repo = job_repo or JobRepository()
        self.book_repo = book_repo or BookRepository()
        self.glossary_repo = glossary_repo or GlossaryRepository()
        self.pipeline = pipeline or TranslationPipeline()
        self.segmenter = SegmentationEngine()

        self._is_paused = False
        self._is_cancelled = False
        self._active_job_id: Optional[str] = None
        self._on_progress_callback: Optional[Callable[[TranslationJob, Optional[Segment]], None]] = None

    def set_progress_callback(self, callback: Callable[[TranslationJob, Optional[Segment]], None]) -> None:
        self._on_progress_callback = callback

    def pause(self) -> None:
        self._is_paused = True
        logger.info("Translation job pause requested.")

    def resume(self) -> None:
        self._is_paused = False
        logger.info("Translation job resumed.")

    def cancel(self) -> None:
        self._is_cancelled = True
        logger.info("Translation job cancel requested.")

    async def run_job(self, job_id: str) -> bool:
        """Executes or resumes a translation job."""
        job = self.job_repo.get_job(job_id)
        if not job:
            logger.error(f"Job {job_id} not found.")
            return False

        self._active_job_id = job_id
        self._is_paused = False
        self._is_cancelled = False

        # Load book
        book = self.book_repo.get_book(job.book_id)
        if not book:
            self.job_repo.update_job_status(job_id, JobStatus.FAILED, "Book not found in database.")
            return False

        # Load glossary
        glossary_profile = (
            self.glossary_repo.get_profile(job.glossary_profile_id)
            if job.glossary_profile_id
            else None
        )
        if not glossary_profile:
            glossary_profile = GlossaryProfile(name="Empty Profile")

        # Load or generate segments
        existing_segments = self.job_repo.get_job_segments(job_id)
        if not existing_segments:
            logger.info("Generating semantic segments for book...")
            all_segments: list[Segment] = []
            order_counter = 0
            for ch in book.chapters:
                ch_segs = self.segmenter.segment_chapter(ch, job_id, start_order_index=order_counter)
                order_counter += len(ch_segs)
                all_segments.extend(ch_segs)

            self.job_repo.save_segments(all_segments)
            existing_segments = all_segments

            # Update job totals
            job.total_chapters = len(book.chapters)
            job.total_segments = len(all_segments)
            job.started_at = datetime.now(timezone.utc)
            self.job_repo.create_job(job)

        self.job_repo.update_job_status(job_id, JobStatus.RUNNING)
        job.status = JobStatus.RUNNING

        # Process each segment
        for idx, segment in enumerate(existing_segments):
            # Check for cancel
            if self._is_cancelled:
                self.job_repo.update_job_status(job_id, JobStatus.CANCELLED)
                job.status = JobStatus.CANCELLED
                if self._on_progress_callback:
                    self._on_progress_callback(job, None)
                return False

            # Check for pause
            while self._is_paused:
                self.job_repo.update_job_status(job_id, JobStatus.PAUSED)
                job.status = JobStatus.PAUSED
                if self._on_progress_callback:
                    self._on_progress_callback(job, None)
                await asyncio.sleep(1.0)
                if self._is_cancelled:
                    self.job_repo.update_job_status(job_id, JobStatus.CANCELLED)
                    return False

            # Skip already completed segments (Resume functionality!)
            if segment.status in (SegmentStatus.TRANSLATED, SegmentStatus.CACHED):
                continue

            # Update current chapter title in job
            chapter = book.get_chapter(segment.chapter_id)
            if chapter:
                job.current_chapter_title = chapter.title

            # Compute context
            ctx_before, ctx_after = self.segmenter.compute_context(existing_segments, idx)

            # Translate
            segment.status = SegmentStatus.TRANSLATING
            self.job_repo.update_segment(segment)

            result = await self.pipeline.translate_segment(
                segment=segment,
                context_before=ctx_before,
                context_after=ctx_after,
                glossary_profile=glossary_profile,
                style_type=job.style,
                source_lang=job.source_language,
                target_lang=job.target_language,
            )

            if result.success:
                segment.translated_text = result.translated_text
                segment.status = SegmentStatus.CACHED if result.cached else SegmentStatus.TRANSLATED
                segment.provider_used = result.provider
                segment.model_used = result.model
                segment.credential_id_used = result.credential_id
                segment.tokens_used = result.tokens_used
                segment.translated_at = datetime.now(timezone.utc)

                job.completed_segments += 1
                if result.cached:
                    job.cached_segments += 1
                job.total_tokens_used += result.tokens_used

                # Update the corresponding blocks in book repository
                for b_id in segment.block_ids:
                    self.book_repo.update_block_translation(b_id, result.translated_text)
            else:
                segment.status = SegmentStatus.FAILED
                segment.error_message = result.error
                job.failed_segments += 1

            # Save segment state atomically
            self.job_repo.update_segment(segment)

            # Update job progress in database
            self.job_repo.update_job_progress(
                job_id=job_id,
                completed_segments=job.completed_segments,
                cached_segments=job.cached_segments,
                failed_segments=job.failed_segments,
                retried_segments=job.retried_segments,
                total_tokens_used=job.total_tokens_used,
                completed_chapters=job.completed_chapters,
                current_chapter_title=job.current_chapter_title,
            )

            # Fire progress callback to UI
            if self._on_progress_callback:
                self._on_progress_callback(job, segment)

            await asyncio.sleep(0.05)

        # Mark job complete
        self.job_repo.update_job_status(job_id, JobStatus.COMPLETED, finished=True)
        job.status = JobStatus.COMPLETED
        if self._on_progress_callback:
            self._on_progress_callback(job, None)
        return True
