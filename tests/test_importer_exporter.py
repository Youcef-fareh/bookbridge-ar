"""Tests for Glossary Import and Export."""

from bookbridge.glossary.importer_exporter import (
    export_glossary_to_csv,
    export_glossary_to_json,
    get_default_xianxia_profile,
    import_glossary_from_csv,
    import_glossary_from_json,
)


def test_glossary_json_roundtrip():
    original = get_default_xianxia_profile()
    json_str = export_glossary_to_json(original)
    imported = import_glossary_from_json(json_str)

    assert imported.name == original.name
    assert len(imported.terms) == len(original.terms)
    assert imported.terms[0].source == original.terms[0].source
    assert imported.terms[0].target == original.terms[0].target


def test_glossary_csv_roundtrip():
    original = get_default_xianxia_profile()
    csv_str = export_glossary_to_csv(original)
    imported = import_glossary_from_csv(csv_str, profile_name="CSV Test")

    assert imported.name == "CSV Test"
    assert len(imported.terms) == len(original.terms)
    assert any(t.source == "Water Spirit" and t.target == "روح الماء" for t in imported.terms)
