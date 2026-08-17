"""Tests for Glossary Engine, Longest-Match Sorting, and Placeholder Protection."""

from bookbridge.config.constants import GlossaryCategory, MatchType
from bookbridge.glossary.engine import GlossaryEngine
from bookbridge.models.glossary import GlossaryProfile, GlossaryTerm


def test_glossary_longest_match_priority():
    profile = GlossaryProfile(name="Cultivation Test")
    profile.terms = [
        GlossaryTerm(
            source="water",
            target="كين",
            category=GlossaryCategory.GENERAL,
            priority=100,
            match_type=MatchType.EXACT,
            case_sensitive=False,
        ),
        GlossaryTerm(
            source="Water Spirit",
            target="روح الماء",
            category=GlossaryCategory.TECHNIQUES,
            priority=150,
            match_type=MatchType.PHRASE,
            case_sensitive=False,
        ),
    ]

    engine = GlossaryEngine(profile)
    source_text = "The Water Spirit summoned ancient water from the river."

    protected_text, token_map = engine.protect_text(source_text)

    # Water Spirit must match first (<NB_TERM_001>) and water second (<NB_TERM_002>)
    assert len(token_map) == 2
    assert "<NB_TERM_001>" in protected_text
    assert "<NB_TERM_002>" in protected_text
    assert token_map["<NB_TERM_001>"] == "روح الماء"
    assert token_map["<NB_TERM_002>"] == "كين"

    # Simulate translation preserving tokens
    simulated_arabic = "استدعى <NB_TERM_001> الـ <NB_TERM_002> القديمة من النهر."
    restored = engine.restore_text(simulated_arabic, token_map)

    assert "روح الماء" in restored
    assert "كين" in restored
    assert "روح كين" not in restored


def test_case_insensitive_matching():
    profile = GlossaryProfile(name="Case Test")
    profile.terms = [
        GlossaryTerm(
            source="water",
            target="ماء",
            case_sensitive=False,
        )
    ]
    engine = GlossaryEngine(profile)
    text = "Water is essential, and WATER flows."
    protected_text, token_map = engine.protect_text(text)
    assert len(token_map) == 1
    token = list(token_map.keys())[0]
    assert protected_text.count(token) == 2


def test_token_validation():
    profile = GlossaryProfile()
    profile.terms = [GlossaryTerm(source="Dantian", target="الدانتين")]
    engine = GlossaryEngine(profile)
    _, token_map = engine.protect_text("His Dantian was damaged.")

    # Missing token case
    raw_bad_arabic = "تضرر جسده بالكامل."
    missing = engine.validate_token_integrity(raw_bad_arabic, token_map)
    assert len(missing) == 1

    # Preserved token case
    raw_good_arabic = "تضرر <NB_TERM_001> الخاص به."
    missing_good = engine.validate_token_integrity(raw_good_arabic, token_map)
    assert len(missing_good) == 0
