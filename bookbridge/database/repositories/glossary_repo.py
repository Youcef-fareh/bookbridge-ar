"""Glossary and Terms Repository."""

import json
from typing import List, Optional
from bookbridge.database.connection import db
from bookbridge.models.glossary import GlossaryProfile, GlossaryTerm
from bookbridge.config.constants import GlossaryCategory, MatchType


class GlossaryRepository:
    def save_profile(self, profile: GlossaryProfile) -> None:
        with db.session() as conn:
            cats_json = json.dumps([c.value for c in profile.enabled_categories])
            rules_json = json.dumps(profile.custom_rules)
            conn.execute(
                """
                INSERT INTO glossaries (id, name, description, genre, enabled_categories_json, custom_rules_json, version, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    description=excluded.description,
                    genre=excluded.genre,
                    enabled_categories_json=excluded.enabled_categories_json,
                    custom_rules_json=excluded.custom_rules_json,
                    version=excluded.version,
                    updated_at=CURRENT_TIMESTAMP;
                """,
                (
                    profile.id,
                    profile.name,
                    profile.description,
                    profile.genre,
                    cats_json,
                    rules_json,
                    profile.version,
                ),
            )

            # Save terms
            for term in profile.terms:
                conn.execute(
                    """
                    INSERT INTO glossary_terms (
                        id, glossary_id, source, target, category, priority, match_type,
                        case_sensitive, locked, enabled, notes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        source=excluded.source,
                        target=excluded.target,
                        category=excluded.category,
                        priority=excluded.priority,
                        match_type=excluded.match_type,
                        case_sensitive=excluded.case_sensitive,
                        locked=excluded.locked,
                        enabled=excluded.enabled,
                        notes=excluded.notes;
                    """,
                    (
                        term.id,
                        profile.id,
                        term.source,
                        term.target,
                        term.category.value,
                        term.priority,
                        term.match_type.value,
                        1 if term.case_sensitive else 0,
                        1 if term.locked else 0,
                        1 if term.enabled else 0,
                        term.notes,
                    ),
                )

    def get_profile(self, profile_id: str) -> Optional[GlossaryProfile]:
        conn = db.get_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM glossaries WHERE id = ?", (profile_id,))
        row = c.fetchone()
        if not row:
            return None

        cats_raw = json.loads(row["enabled_categories_json"]) if row["enabled_categories_json"] else []
        enabled_cats = [GlossaryCategory(c) for c in cats_raw if c in [e.value for e in GlossaryCategory]]
        rules = json.loads(row["custom_rules_json"]) if row["custom_rules_json"] else {}

        profile = GlossaryProfile(
            id=row["id"],
            name=row["name"],
            description=row["description"] or "",
            genre=row["genre"] or "General",
            enabled_categories=enabled_cats if enabled_cats else list(GlossaryCategory),
            custom_rules=rules,
            version=row["version"],
        )

        c.execute("SELECT * FROM glossary_terms WHERE glossary_id = ? ORDER BY priority DESC, length(source) DESC", (profile_id,))
        for term_row in c.fetchall():
            term = GlossaryTerm(
                id=term_row["id"],
                glossary_id=term_row["glossary_id"],
                source=term_row["source"],
                target=term_row["target"],
                category=GlossaryCategory(term_row["category"]),
                priority=term_row["priority"],
                match_type=MatchType(term_row["match_type"]),
                case_sensitive=bool(term_row["case_sensitive"]),
                locked=bool(term_row["locked"]),
                enabled=bool(term_row["enabled"]),
                notes=term_row["notes"],
            )
            profile.terms.append(term)

        return profile

    def list_profiles(self) -> List[GlossaryProfile]:
        conn = db.get_connection()
        c = conn.cursor()
        c.execute("SELECT id FROM glossaries ORDER BY updated_at DESC")
        profiles = []
        for row in c.fetchall():
            prof = self.get_profile(row["id"])
            if prof:
                profiles.append(prof)
        return profiles

    def delete_term(self, term_id: str) -> None:
        with db.session() as conn:
            conn.execute("DELETE FROM glossary_terms WHERE id = ?", (term_id,))

    def delete_profile(self, profile_id: str) -> None:
        with db.session() as conn:
            conn.execute("DELETE FROM glossaries WHERE id = ?", (profile_id,))
