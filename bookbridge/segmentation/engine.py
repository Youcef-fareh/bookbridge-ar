"""Segmentation and Context Engine.

Splits chapters into semantic chunks respecting paragraph boundaries,
computes context windows (before/after), and generates deterministic cache keys.
"""

import hashlib
import json
from typing import List
from bookbridge.config.constants import BlockType
from bookbridge.models.book import Chapter
from bookbridge.models.job import Segment
from bookbridge.models.style import TranslationStyleType


class SegmentationEngine:
    def __init__(
        self,
        max_chars: int = 1200,
        context_blocks_count: int = 2,
    ):
        self.max_chars = max_chars
        self.context_blocks_count = context_blocks_count

    def segment_chapter(
        self,
        chapter: Chapter,
        job_id: str,
        start_order_index: int = 0,
    ) -> List[Segment]:
        """Segments a chapter into translatable segments linked to block IDs."""
        translatable_blocks = [b for b in chapter.blocks if b.has_translatable_text]
        if not translatable_blocks:
            return []

        segments: List[Segment] = []
        current_block_ids: List[str] = []
        current_texts: List[str] = []
        current_char_count = 0
        order_idx = start_order_index

        for block in translatable_blocks:
            block_text = block.source_text.strip()
            if not block_text:
                continue

            # Headings always start their own segment or separate chunk
            is_heading = block.type == BlockType.HEADING

            if current_block_ids and (
                is_heading or (current_char_count + len(block_text) > self.max_chars)
            ):
                combined_text = "\n\n".join(current_texts)
                src_hash = hashlib.sha256(combined_text.encode("utf-8")).hexdigest()
                segments.append(
                    Segment(
                        job_id=job_id,
                        chapter_id=chapter.id,
                        block_ids=list(current_block_ids),
                        order_index=order_idx,
                        source_text=combined_text,
                        source_hash=src_hash,
                    )
                )
                order_idx += 1
                current_block_ids = []
                current_texts = []
                current_char_count = 0

            current_block_ids.append(block.id)
            current_texts.append(block_text)
            current_char_count += len(block_text)

            if is_heading:
                # Flush heading immediately
                combined_text = "\n\n".join(current_texts)
                src_hash = hashlib.sha256(combined_text.encode("utf-8")).hexdigest()
                segments.append(
                    Segment(
                        job_id=job_id,
                        chapter_id=chapter.id,
                        block_ids=list(current_block_ids),
                        order_index=order_idx,
                        source_text=combined_text,
                        source_hash=src_hash,
                    )
                )
                order_idx += 1
                current_block_ids = []
                current_texts = []
                current_char_count = 0

        if current_block_ids:
            combined_text = "\n\n".join(current_texts)
            src_hash = hashlib.sha256(combined_text.encode("utf-8")).hexdigest()
            segments.append(
                Segment(
                    job_id=job_id,
                    chapter_id=chapter.id,
                    block_ids=list(current_block_ids),
                    order_index=order_idx,
                    source_text=combined_text,
                    source_hash=src_hash,
                )
            )

        return segments

    def compute_context(
        self, segments: List[Segment], current_idx: int
    ) -> tuple[str, str]:
        """Extracts preceding and upcoming context strings for segment at current_idx."""
        before_parts = []
        for i in range(max(0, current_idx - self.context_blocks_count), current_idx):
            before_parts.append(segments[i].source_text)

        after_parts = []
        for i in range(current_idx + 1, min(len(segments), current_idx + 1 + self.context_blocks_count)):
            after_parts.append(segments[i].source_text)

        context_before = "\n\n".join(before_parts)
        context_after = "\n\n".join(after_parts)
        return context_before, context_after

    @staticmethod
    def generate_cache_key(
        source_text: str,
        context_before: str,
        context_after: str,
        source_lang: str,
        target_lang: str,
        glossary_version: int,
        style: TranslationStyleType,
        prompt_version: int = 1,
    ) -> str:
        """Generates a deterministic SHA-256 cache key for the exact translation request."""
        payload = {
            "src": source_text.strip(),
            "ctx_b": context_before.strip(),
            "ctx_a": context_after.strip(),
            "sl": source_lang,
            "tl": target_lang,
            "gv": glossary_version,
            "style": style.value,
            "pv": prompt_version,
        }
        key_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")
        return hashlib.sha256(key_bytes).hexdigest()
