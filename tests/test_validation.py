"""Tests for Output Validation Engine."""

from bookbridge.validation.engine import ValidationEngine


def test_validation_empty_output():
    is_valid, errors = ValidationEngine.validate_translation(
        source_text="Hello world",
        raw_translated_text="",
        token_to_target={},
    )
    assert is_valid is False
    assert any("empty" in e.lower() for e in errors)


def test_validation_missing_tokens():
    token_map = {"<NB_TERM_001>": "روح السيف", "<NB_TERM_002>": "كين"}
    is_valid, errors = ValidationEngine.validate_translation(
        source_text="The Sword Spirit commanded water.",
        raw_translated_text="أمر <NB_TERM_001> بالسير.",
        token_to_target=token_map,
    )
    assert is_valid is False
    assert any("NB_TERM_002" in e for e in errors)


def test_validation_success():
    token_map = {"<NB_TERM_001>": "روح السيف"}
    is_valid, errors = ValidationEngine.validate_translation(
        source_text="The Sword Spirit appeared in Chapter 14.",
        raw_translated_text="ظهر <NB_TERM_001> في الفصل 14.",
        token_to_target=token_map,
    )
    assert is_valid is True
    assert len(errors) == 0
