"""Glossary Import/Export and Built-in Profiles."""

import csv
import io
import json
from typing import List
from bookbridge.config.constants import GlossaryCategory, MatchType
from bookbridge.models.glossary import GlossaryProfile, GlossaryTerm


def get_default_xianxia_profile() -> GlossaryProfile:
    profile = GlossaryProfile(
        name="Xianxia & Cultivation Preset",
        description="Terminology preset for Chinese cultivation and martial arts novels.",
        genre="Xianxia",
    )
    preset_terms = [
        ("Water Spirit", "روح الماء", GlossaryCategory.TECHNIQUES, 150, MatchType.PHRASE),
        ("Sword Spirit", "روح السيف", GlossaryCategory.TECHNIQUES, 150, MatchType.PHRASE),
        ("Heavenly Sword", "السيف السماوي", GlossaryCategory.ITEMS, 150, MatchType.PHRASE),
        ("Storage Ring", "خاتم التخزين", GlossaryCategory.ITEMS, 120, MatchType.PHRASE),
        ("Qi Condensation", "تكثيف التشي", GlossaryCategory.CULTIVATION, 120, MatchType.PHRASE),
        ("Foundation Establishment", "تأسيس الأساس", GlossaryCategory.CULTIVATION, 120, MatchType.PHRASE),
        ("Core Formation", "تشكيل النواة", GlossaryCategory.CULTIVATION, 120, MatchType.PHRASE),
        ("Nascent Soul", "الروح الوليدة", GlossaryCategory.CULTIVATION, 120, MatchType.PHRASE),
        ("Spirit Stone", "حجر روحي", GlossaryCategory.ITEMS, 110, MatchType.PHRASE),
        ("Dantian", "الدانتين", GlossaryCategory.CULTIVATION, 100, MatchType.EXACT),
        ("Qi", "التشي", GlossaryCategory.CULTIVATION, 100, MatchType.EXACT),
        ("Dao", "الداو", GlossaryCategory.CULTIVATION, 100, MatchType.EXACT),
        ("Karma", "الكارما", GlossaryCategory.GENERAL, 90, MatchType.EXACT),
    ]
    for src, tgt, cat, pri, mt in preset_terms:
        profile.terms.append(
            GlossaryTerm(
                glossary_id=profile.id,
                source=src,
                target=tgt,
                category=cat,
                priority=pri,
                match_type=mt,
            )
        )
    return profile


def export_glossary_to_json(profile: GlossaryProfile) -> str:
    return json.dumps(profile.model_dump(), indent=2, ensure_ascii=False)


def export_glossary_to_csv(profile: GlossaryProfile) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["source", "target", "category", "priority", "match_type", "case_sensitive", "locked", "notes"])
    for t in profile.terms:
        writer.writerow([
            t.source,
            t.target,
            t.category.value,
            t.priority,
            t.match_type.value,
            "1" if t.case_sensitive else "0",
            "1" if t.locked else "0",
            t.notes or "",
        ])
    return output.getvalue()


def import_glossary_from_json(json_content: str) -> GlossaryProfile:
    data = json.loads(json_content)
    return GlossaryProfile.model_validate(data)


def import_glossary_from_csv(csv_content: str, profile_name: str = "Imported Glossary") -> GlossaryProfile:
    profile = GlossaryProfile(name=profile_name)
    reader = csv.DictReader(io.StringIO(csv_content))
    for row in reader:
        source = row.get("source", "").strip()
        target = row.get("target", "").strip()
        if not source or not target:
            continue
        cat_str = row.get("category", GlossaryCategory.GENERAL.value)
        try:
            category = GlossaryCategory(cat_str)
        except ValueError:
            category = GlossaryCategory.GENERAL
        
        priority = int(row.get("priority", 100))
        match_type = MatchType(row.get("match_type", MatchType.EXACT.value))
        case_sensitive = row.get("case_sensitive", "0") in ("1", "true", "True")
        locked = row.get("locked", "1") in ("1", "true", "True")
        notes = row.get("notes", None)

        profile.terms.append(
            GlossaryTerm(
                glossary_id=profile.id,
                source=source,
                target=target,
                category=category,
                priority=priority,
                match_type=match_type,
                case_sensitive=case_sensitive,
                locked=locked,
                notes=notes,
            )
        )
    return profile
