"""Core Translation Pipeline Orchestrator."""

import logging
from datetime import datetime
from typing import Optional
from bookbridge.config.constants import DEFAULT_MAX_RETRIES, ProviderType
from bookbridge.database.repositories.memory_repo import MemoryRepository
from bookbridge.glossary.engine import GlossaryEngine
from bookbridge.models.glossary import GlossaryProfile
from bookbridge.models.job import Segment, TranslationResult
from bookbridge.models.style import STYLE_PRESETS, StylePromptConfig, TranslationStyleType
from bookbridge.routing.router import TranslationRouter
from bookbridge.segmentation.engine import SegmentationEngine
from bookbridge.validation.engine import ValidationEngine

logger = logging.getLogger(__name__)


class TranslationPipeline:
    def __init__(
        self,
        router: Optional[TranslationRouter] = None,
        memory_repo: Optional[MemoryRepository] = None,
    ):
        self.router = router or TranslationRouter()
        self.memory_repo = memory_repo or MemoryRepository()

    async def translate_segment(
        self,
        segment: Segment,
        context_before: str,
        context_after: str,
        glossary_profile: GlossaryProfile,
        style_type: TranslationStyleType = TranslationStyleType.NATURAL,
        preferred_provider: Optional[ProviderType] = None,
        source_lang: str = "en",
        target_lang: str = "ar",
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> TranslationResult:
        """Executes full translation pipeline for a single segment."""
        style_config = STYLE_PRESETS.get(style_type, STYLE_PRESETS[TranslationStyleType.NATURAL])
        glossary_engine = GlossaryEngine(glossary_profile)

        # 1. Deterministic Cache Key Check
        cache_key = SegmentationEngine.generate_cache_key(
            source_text=segment.source_text,
            context_before=context_before,
            context_after=context_after,
            source_lang=source_lang,
            target_lang=target_lang,
            glossary_version=glossary_profile.version,
            style=style_type,
        )
        segment.cache_key = cache_key

        cached_text = self.memory_repo.get_cache_entry(cache_key)
        if cached_text:
            logger.info(f"Segment {segment.order_index} request cache HIT.")
            return TranslationResult(
                success=True,
                translated_text=cached_text,
                source_text=segment.source_text,
                cached=True,
            )

        # 2. Translation Memory (Exact sentence match) Check
        tm_match = self.memory_repo.find_tm_match(segment.source_text, source_lang, target_lang)
        if tm_match:
            logger.info(f"Segment {segment.order_index} Translation Memory HIT.")
            # Cache this request as well for future speed
            self.memory_repo.save_cache_entry(cache_key, tm_match, provider="tm", model="exact_match")
            return TranslationResult(
                success=True,
                translated_text=tm_match,
                source_text=segment.source_text,
                cached=True,
            )

        # 3. Glossary Term Protection (Mask terms into <NB_TERM_XXX>)
        protected_text, token_to_target = glossary_engine.protect_text(segment.source_text)

        # 4. Routing & Translation with Validation Retries
        attempts = 0
        last_result = None

        while attempts <= max_retries:
            attempts += 1
            result = await self.router.translate_with_failover(
                text=protected_text,
                context_before=context_before,
                context_after=context_after,
                style_config=style_config,
                preferred_provider=preferred_provider,
                source_lang=source_lang,
                target_lang=target_lang,
                job_id=segment.job_id,
                segment_id=segment.id,
            )

            if not result.success:
                last_result = result
                if not result.retryable:
                    break
                continue

            # 5. Validation Check
            is_valid, val_errors = ValidationEngine.validate_translation(
                source_text=segment.source_text,
                raw_translated_text=result.translated_text,
                token_to_target=token_to_target,
            )

            if is_valid:
                # 6. Unmask & Restore Protected Glossary Terms
                final_arabic_text = glossary_engine.restore_text(
                    result.translated_text, token_to_target
                )
                result.translated_text = final_arabic_text

                # 7. Commit to Cache & Translation Memory
                self.memory_repo.save_cache_entry(
                    cache_key=cache_key,
                    translated_text=final_arabic_text,
                    provider=result.provider,
                    model=result.model,
                    tokens_used=result.tokens_used,
                )
                self.memory_repo.save_tm_entry(
                    source_text=segment.source_text,
                    translated_text=final_arabic_text,
                    source_lang=source_lang,
                    target_lang=target_lang,
                    glossary_version=glossary_profile.version,
                    style_type=style_type.value,
                    provider=result.provider,
                    model=result.model,
                )

                return result
            else:
                logger.warning(
                    f"Segment {segment.order_index} validation failed (attempt {attempts}/{max_retries + 1}): {', '.join(val_errors)}"
                )
                result.validation_errors = val_errors
                last_result = result

        # If all retries failed validation, return last result marked as needing review
        if last_result and last_result.translated_text:
            final_arabic_text = glossary_engine.restore_text(
                last_result.translated_text, token_to_target
            )
            last_result.translated_text = final_arabic_text
        return last_result or TranslationResult(
            success=False,
            source_text=segment.source_text,
            error="Translation attempts failed.",
        )
