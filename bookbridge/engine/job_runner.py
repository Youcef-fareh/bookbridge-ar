"""Async Job Runner for Book Translation with Pause, Resume, and Event Hooks."""

import asyncio
from datetime import datetime, timezone
import logging
from typing import Callable, Optional
from bookbridge.config.constants import JobStatus, ProviderType, SegmentStatus
from bookbridge.config.settings import settings
from bookbridge.database.repositories.book_repo import BookRepository
from bookbridge.database.repositories.glossary_repo import GlossaryRepository
from bookbridge.database.repositories.job_repo import JobRepository
from bookbridge.engine.translator import TranslationPipeline
from bookbridge.glossary.engine import GlossaryEngine
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
        self.segmenter = SegmentationEngine(
            max_chars=settings.max_segment_chars,
            context_blocks_count=settings.context_window_blocks,
        )

        self._is_paused = False
        self._is_cancelled = False
        self._active_job_id: Optional[str] = None
        self._on_progress_callback: Optional[Callable[[TranslationJob, Optional[Segment]], None]] = None

    # -------------------------------------------------------------------------
    # Public control API
    # -------------------------------------------------------------------------

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

    def reset_control(self) -> None:
        """Clear pause/cancel flags before starting a brand-new worker.

        This is deliberately called by the bridge before ``QThread.start``,
        not inside the worker: a cancel clicked while the job is still QUEUED
        must not be erased when the worker thread begins executing.
        """
        self._is_paused = False
        self._is_cancelled = False

    # -------------------------------------------------------------------------
    # Private helpers
    # -------------------------------------------------------------------------

    def _notify(self, job: TranslationJob, segment: Optional[Segment] = None) -> None:
        """Fire the progress callback if one is registered."""
        if self._on_progress_callback:
            self._on_progress_callback(job, segment)

    @staticmethod
    def _sync_job_counters(job: TranslationJob, segments: list[Segment]) -> None:
        """Recompute counters from segment state.

        Resumed jobs can have a segment that failed in an earlier run. Simply
        incrementing ``completed_segments`` while leaving ``failed_segments``
        untouched makes a fully successful resume look like a failure forever.
        """
        job.total_segments = len(segments)
        job.completed_segments = sum(
            1
            for segment in segments
            if segment.status in (SegmentStatus.TRANSLATED, SegmentStatus.CACHED)
        )
        job.cached_segments = sum(
            1 for segment in segments if segment.status == SegmentStatus.CACHED
        )
        job.failed_segments = sum(
            1
            for segment in segments
            if segment.status in (SegmentStatus.FAILED, SegmentStatus.NEEDS_REVIEW)
        )
        job.total_tokens_used = sum(segment.tokens_used for segment in segments)

    def _persist_progress(self, job: TranslationJob) -> None:
        self.job_repo.update_job_progress(
            job_id=job.id,
            completed_segments=job.completed_segments,
            cached_segments=job.cached_segments,
            failed_segments=job.failed_segments,
            retried_segments=job.retried_segments,
            total_tokens_used=job.total_tokens_used,
            completed_chapters=job.completed_chapters,
            current_chapter_title=job.current_chapter_title,
            total_segments=job.total_segments,
        )

    def _set_status(
        self,
        job: TranslationJob,
        status: JobStatus,
        error: Optional[str] = None,
        finished: bool = False,
    ) -> None:
        """Update both in-memory job state and the database atomically."""
        job.status = status
        if error:
            job.error_message = error
        self.job_repo.update_job_status(job.id, status, error_message=error, finished=finished)

    # -------------------------------------------------------------------------
    # Main execution
    # -------------------------------------------------------------------------

    async def run_job(self, job_id: str) -> bool:
        """Execute or resume a translation job.

        Unexpected exceptions are logged with a traceback and persisted as a
        failed job instead of leaving the UI stuck on "running" forever.
        """
        try:
            return await self._run_job(job_id)
        except asyncio.CancelledError:
            logger.warning("Job %s was cancelled at the asyncio level.", job_id)
            raise
        except Exception as exc:
            logger.exception("Job %s crashed unexpectedly.", job_id)
            try:
                job = self.job_repo.get_job(job_id)
                if job:
                    self._set_status(
                        job,
                        JobStatus.FAILED,
                        f"Unexpected error: {exc}",
                        finished=True,
                    )
                    self._notify(job)
            except Exception:
                logger.exception("Could not mark job %s as failed.", job_id)
            return False

    async def _run_job(self, job_id: str) -> bool:
        """Executes or resumes a translation job. Returns True on full success."""
        job = self.job_repo.get_job(job_id)
        if not job:
            logger.error(f"Job {job_id} not found.")
            return False

        self._active_job_id = job_id
        logger.info(
            "Starting job %s for book '%s' (id=%s, style=%s, glossary=%s, strategy=%s).",
            job.id,
            job.book_title,
            job.book_id,
            job.style.value,
            job.glossary_profile_id or "none",
            (job.custom_settings or {}).get("strategy", "auto"),
        )

        if self._is_cancelled:
            self._set_status(job, JobStatus.CANCELLED)
            self._notify(job)
            return False

        # Load book
        book = self.book_repo.get_book(job.book_id)
        if not book:
            self._set_status(job, JobStatus.FAILED, "Book not found in database.")
            return False

        # Load glossary (or use an empty profile when none is set)
        glossary_profile: GlossaryProfile
        if job.glossary_profile_id:
            glossary_profile = self.glossary_repo.get_profile(job.glossary_profile_id) or GlossaryProfile(name="Empty Profile")
        else:
            glossary_profile = GlossaryProfile(name="Empty Profile")

        # Build a single GlossaryEngine for the entire job so regex patterns
        # are sorted and compiled once rather than on every segment call.
        glossary_engine = GlossaryEngine(glossary_profile)

        # A resumed job is working immediately, including while it rebuilds
        # segments. Do not leave it looking PAUSED (which would offer Resume
        # again) for the whole segmentation pass on a large book.
        if job.status in (
            JobStatus.PAUSED,
            JobStatus.CANCELLED,
            JobStatus.NEEDS_REVIEW,
            JobStatus.FAILED,
        ):
            self.job_repo.clear_job_error(job_id)
            job.error_message = None
            self._set_status(job, JobStatus.RUNNING)
            self._notify(job)

        # Determine preferred provider from job's custom_settings (set by UI)
        strategy = job.custom_settings.get("strategy") if job.custom_settings else None
        preferred_provider: Optional[ProviderType | str] = None
        if strategy and strategy != "auto":
            try:
                preferred_provider = ProviderType(strategy)
            except ValueError:
                preferred_provider = strategy  # custom provider string ID

        # Load or generate segments
        existing_segments = self.job_repo.get_job_segments(job_id)
        if not existing_segments:
            # Refresh segmenter params in case settings changed since init
            self.segmenter = SegmentationEngine(
                max_chars=settings.max_segment_chars,
                context_blocks_count=settings.context_window_blocks,
            )
            logger.info(
                "Generating semantic segments for '%s' (%d chapters)...",
                job.book_title,
                len(book.chapters),
            )
            all_segments: list[Segment] = []
            order_counter = 0
            chapter_total = max(1, len(book.chapters))
            for chapter_index, ch in enumerate(book.chapters, start=1):
                if self._is_cancelled:
                    # Do not persist a partially segmented book: resuming a
                    # job with only the first N chapters would silently skip
                    # the rest of the book.
                    logger.info("Job %s cancelled during segmentation.", job.id)
                    self._set_status(job, JobStatus.CANCELLED)
                    self._notify(job)
                    return False
                ch_segs = self.segmenter.segment_chapter(ch, job_id, start_order_index=order_counter)
                order_counter += len(ch_segs)
                all_segments.extend(ch_segs)
                # Give the UI something to show while long books are segmented.
                job.total_chapters = len(book.chapters)
                job.total_segments = len(all_segments)
                job.current_chapter_title = ch.title
                if chapter_index == len(book.chapters) or chapter_index % 5 == 0:
                    self._notify(job)
                    logger.info(
                        "Segmentation progress: %d/%d chapters, %d segments.",
                        chapter_index,
                        chapter_total,
                        len(all_segments),
                    )

            self.job_repo.save_segments(all_segments)
            existing_segments = all_segments

            job.total_chapters = len(book.chapters)
            job.total_segments = len(all_segments)
            job.started_at = datetime.now(timezone.utc)
            self.job_repo.create_job(job)
            logger.info(
                "Job %s segmented into %d segment(s) across %d chapter(s).",
                job.id,
                len(all_segments),
                len(book.chapters),
            )
            self._notify(job)

        # Resuming an earlier job: rebuild counters from the persisted segment
        # states instead of trusting an older, possibly stale job row.
        job.total_chapters = len(book.chapters)
        self._sync_job_counters(job, existing_segments)
        self.job_repo.clear_job_error(job_id)
        job.error_message = None
        self._persist_progress(job)

        self._set_status(job, JobStatus.RUNNING)
        self._notify(job)
        logger.info(
            "Job %s running: %d segment(s), %d already done.",
            job.id,
            len(existing_segments),
            sum(
                1
                for item in existing_segments
                if item.status in (SegmentStatus.TRANSLATED, SegmentStatus.CACHED)
            ),
        )

        # ------------------------------------------------------------------ #
        # Main translation loop                                                #
        # ------------------------------------------------------------------ #
        for idx, segment in enumerate(existing_segments):

            # --- Cancel check ---
            if self._is_cancelled:
                self._set_status(job, JobStatus.CANCELLED)
                self._notify(job)
                return False

            # --- Pause loop ---
            if self._is_paused:
                self._set_status(job, JobStatus.PAUSED)
                self._notify(job)
                while self._is_paused:
                    await asyncio.sleep(1.0)
                    if self._is_cancelled:
                        self._set_status(job, JobStatus.CANCELLED)
                        self._notify(job)
                        return False
                # Resumed — restore RUNNING status
                self._set_status(job, JobStatus.RUNNING)
                self._notify(job)

            # Skip already completed segments (resume functionality)
            if segment.status in (SegmentStatus.TRANSLATED, SegmentStatus.CACHED):
                continue

            # Update chapter context in job
            chapter = book.get_chapter(segment.chapter_id)
            if chapter:
                job.current_chapter_title = chapter.title

            # Compute surrounding context
            ctx_before, ctx_after = self.segmenter.compute_context(existing_segments, idx)

            # Mark segment as in-flight
            previous_status = segment.status
            segment.status = SegmentStatus.TRANSLATING
            self.job_repo.update_segment(segment)
            logger.debug(
                "Job %s: segment %d/%d order=%d chapter=%r chars=%d",
                job.id,
                idx + 1,
                len(existing_segments),
                segment.order_index,
                job.current_chapter_title,
                len(segment.source_text),
            )

            result = await self.pipeline.translate_segment(
                segment=segment,
                context_before=ctx_before,
                context_after=ctx_after,
                glossary_profile=glossary_profile,
                glossary_engine=glossary_engine,
                style_type=job.style,
                preferred_provider=preferred_provider,
                source_lang=job.source_language,
                target_lang=job.target_language,
                max_retries=settings.max_validation_retries,
                cancel_check=lambda: self._is_cancelled,
            )

            # --- Handle cancellation signalled from inside the pipeline ---
            if result.cancelled or self._is_cancelled:
                segment.status = SegmentStatus.PENDING
                segment.error_message = "Translation cancelled by user."
                self.job_repo.update_segment(segment)
                self._set_status(job, JobStatus.CANCELLED)
                self._notify(job)
                return False

            # --- Record result ---
            if result.success:
                segment.translated_text = result.translated_text
                segment.status = SegmentStatus.CACHED if result.cached else SegmentStatus.TRANSLATED
                segment.provider_used = result.provider
                segment.model_used = result.model
                segment.credential_id_used = result.credential_id
                segment.tokens_used = result.tokens_used
                segment.translated_at = datetime.now(timezone.utc)

                job.completed_segments += 1
                if previous_status in (SegmentStatus.FAILED, SegmentStatus.NEEDS_REVIEW):
                    # This segment was counted as failed by an earlier run.
                    job.failed_segments = max(0, job.failed_segments - 1)
                if result.cached:
                    job.cached_segments += 1
                job.total_tokens_used += result.tokens_used

                for b_id in segment.block_ids:
                    self.book_repo.update_block_translation(b_id, result.translated_text)
                logger.info(
                    "Job %s: segment %d/%d translated%s via %s/%s (%d tokens).",
                    job.id,
                    idx + 1,
                    len(existing_segments),
                    " from cache" if result.cached else "",
                    result.provider or "unknown",
                    result.model or "unknown",
                    result.tokens_used,
                )
            else:
                segment.status = SegmentStatus.FAILED
                segment.error_message = result.error
                job.failed_segments += 1
                logger.error(
                    "Job %s: segment %d/%d FAILED after retries: %s",
                    job.id,
                    idx + 1,
                    len(existing_segments),
                    result.error or "unknown provider error",
                )

            # Persist segment and progress together
            self.job_repo.update_segment(segment)
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
            self._notify(job, segment)

            # Stop immediately on non-retryable failure
            if not result.success:
                message = (
                    f"Translation stopped after the allowed attempts: "
                    f"{result.error or 'unknown provider error'}"
                )
                self._set_status(job, JobStatus.NEEDS_REVIEW, message)
                self._notify(job)
                return False

            # Honour user-configured inter-request cooldown
            cooldown = max(0.0, float(getattr(settings, "normal_request_cooldown_seconds", 0.05)))
            if cooldown > 0:
                await asyncio.sleep(cooldown)

        # ------------------------------------------------------------------ #
        # Post-loop outcome                                                    #
        # ------------------------------------------------------------------ #
        # Recompute from segment state so a successful resume clears failures
        # from the previous run, even if a counter was left stale in SQLite.
        self._sync_job_counters(job, existing_segments)
        self._persist_progress(job)
        if job.failed_segments:
            message = (
                f"Translation finished with {job.failed_segments} failed segment(s). "
                "Resolve provider errors and resume the job."
            )
            logger.warning("Job %s needs review: %s", job.id, message)
            self._set_status(job, JobStatus.NEEDS_REVIEW, message)
            self._notify(job)
            return False

        logger.info(
            "Job %s completed: %d segment(s), %d cached, %d tokens.",
            job.id,
            job.completed_segments,
            job.cached_segments,
            job.total_tokens_used,
        )
        self._set_status(job, JobStatus.COMPLETED, finished=True)
        self._notify(job)
        return True
