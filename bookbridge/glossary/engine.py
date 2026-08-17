"""Glossary & Protected Terminology Engine.

Performs deterministic terminology protection using safe placeholder tokens,
longest-match & priority sorting, and post-translation restoration.
"""

import re
from typing import Dict, List, Tuple
from bookbridge.config.constants import MatchType, TOKEN_PATTERN, TOKEN_PREFIX, TOKEN_SUFFIX
from bookbridge.models.glossary import GlossaryProfile, GlossaryTerm


class GlossaryEngine:
    def __init__(self, profile: GlossaryProfile):
        self.profile = profile

    def _get_sorted_active_terms(self) -> List[GlossaryTerm]:
        """Sort terms by priority DESC, then by length of source phrase DESC."""
        terms = self.profile.active_terms()
        # Sort key: (-priority, -length, source)
        return sorted(terms, key=lambda t: (-t.priority, -len(t.source), t.source))

    def protect_text(self, text: str) -> Tuple[str, Dict[str, str]]:
        """
        Replaces glossary terms in source text with protected tokens.
        
        Returns:
            (protected_text, token_to_target_map)
        """
        if not text:
            return "", {}

        sorted_terms = self._get_sorted_active_terms()
        if not sorted_terms:
            return text, {}

        token_to_target: Dict[str, str] = {}
        token_counter = 1
        result_text = text

        for term in sorted_terms:
            target_arabic = term.target.strip()
            if not target_arabic:
                continue

            if term.match_type == MatchType.EXACT:
                # Word boundary match
                flags = 0 if term.case_sensitive else re.IGNORECASE
                pattern = r"\b" + re.escape(term.source.strip()) + r"\b"
            elif term.match_type == MatchType.PHRASE:
                flags = 0 if term.case_sensitive else re.IGNORECASE
                pattern = re.escape(term.source.strip())
            elif term.match_type == MatchType.REGEX:
                flags = 0 if term.case_sensitive else re.IGNORECASE
                pattern = term.source.strip()
            else:
                flags = 0 if term.case_sensitive else re.IGNORECASE
                pattern = r"\b" + re.escape(term.source.strip()) + r"\b"

            try:
                compiled = re.compile(pattern, flags)
            except re.error:
                continue

            # Check if this term matches
            if compiled.search(result_text):
                token = f"{TOKEN_PREFIX}{token_counter:03d}{TOKEN_SUFFIX}"
                token_counter += 1
                token_to_target[token] = target_arabic

                # Replace all matches with the protected token
                result_text = compiled.sub(token, result_text)

        return result_text, token_to_target

    def restore_text(self, translated_text: str, token_to_target: Dict[str, str]) -> str:
        """
        Restores protected tokens back into their configured Arabic target terms.
        Handles variations where AI might add spaces inside tokens like `< NB_TERM_001 >`.
        """
        if not translated_text:
            return ""

        restored = translated_text
        for token, target_term in token_to_target.items():
            # Exact token replacement
            if token in restored:
                restored = restored.replace(token, target_term)
            else:
                # Fuzzy replacement for slightly modified token format like < NB_TERM_001 > or [[NB_TERM_001]]
                match = re.search(r"(\d+)", token)
                if match:
                    num = match.group(1)
                    fuzzy_pattern = rf"<\s*NB_TERM_{num}\s*>|\[\[\s*NB_TERM_{num}\s*\]\]|\[\s*NB_TERM_{num}\s*\]"
                    restored = re.sub(fuzzy_pattern, target_term, restored)

        return restored

    def validate_token_integrity(
        self, raw_translated_text: str, token_to_target: Dict[str, str]
    ) -> List[str]:
        """Checks if all protected tokens sent to LLM were returned in the translated output."""
        missing = []
        for token in token_to_target.keys():
            match = re.search(r"(\d+)", token)
            if not match:
                continue
            num = match.group(1)
            fuzzy_pattern = rf"<\s*NB_TERM_{num}\s*>|\[\[\s*NB_TERM_{num}\s*\]\]|\[\s*NB_TERM_{num}\s*\]|NB_TERM_{num}"
            if not re.search(fuzzy_pattern, raw_translated_text):
                missing.append(token)
        return missing
