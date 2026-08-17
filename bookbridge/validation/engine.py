"""Validation Engine for Translation Quality and Structural Integrity."""

import re
from typing import Dict, List, Tuple


class ValidationEngine:
    @staticmethod
    def validate_translation(
        source_text: str,
        raw_translated_text: str,
        token_to_target: Dict[str, str],
        max_length_ratio: float = 4.0,
        min_length_ratio: float = 0.15,
    ) -> Tuple[bool, List[str]]:
        """
        Validates raw translated text before token unmasking.
        
        Returns:
            (is_valid, list_of_error_reasons)
        """
        errors: List[str] = []

        # 1. Empty Check
        if not raw_translated_text or not raw_translated_text.strip():
            errors.append("Translated text is empty.")
            return False, errors

        # 2. Token Integrity Check (Crucial for Glossary compliance)
        for token in token_to_target.keys():
            # Check for standard or slightly spaced token format
            match = re.search(r"(\d+)", token)
            if match:
                num = match.group(1)
                fuzzy_pattern = rf"<\s*NB_TERM_{num}\s*>|\[\[\s*NB_TERM_{num}\s*\]\]|\[\s*NB_TERM_{num}\s*\]|NB_TERM_{num}"
                if not re.search(fuzzy_pattern, raw_translated_text):
                    errors.append(f"Missing protected glossary token: {token}")

        # 3. Length Anomaly Detection
        src_len = len(source_text.strip())
        trans_len = len(raw_translated_text.strip())

        if src_len > 30:
            ratio = trans_len / float(src_len)
            if ratio < min_length_ratio:
                errors.append(f"Suspiciously short translation (ratio {ratio:.2f} < {min_length_ratio})")
            elif ratio > max_length_ratio:
                errors.append(f"Suspiciously long translation (ratio {ratio:.2f} > {max_length_ratio})")

        # 4. Number Preservation Check
        # Extract standalone numbers from source
        src_numbers = set(re.findall(r"\b\d+\b", source_text))
        if src_numbers:
            # Check if numbers (either western or eastern Arabic numerals) are preserved
            trans_numbers = set(re.findall(r"\b\d+\b", raw_translated_text))
            # Convert Arabic-Indic numerals if any
            arabic_indic_map = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
            trans_converted = {n.translate(arabic_indic_map) for n in trans_numbers}
            missing_numbers = src_numbers - trans_converted
            # If large numbers or multiple numbers are missing, flag warning/error
            if len(missing_numbers) > 1 and src_len < 300:
                errors.append(f"Source numbers missing in translation: {', '.join(list(missing_numbers)[:3])}")

        is_valid = len(errors) == 0
        return is_valid, errors
