"""Provider Credential Metadata and Usage Repository."""

from datetime import datetime
import json
from typing import List, Optional
from bookbridge.database.connection import db
from bookbridge.models.provider import ProviderCredentialMetadata, UsageRecord
from bookbridge.config.constants import CredentialState, ProviderType


def _to_iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def _from_iso(val: Optional[str]) -> Optional[datetime]:
    if not val:
        return None
    if isinstance(val, datetime):
        return val
    try:
        return datetime.fromisoformat(val)
    except Exception:
        return None


class CredentialRepository:
    def save_credential_metadata(self, cred: ProviderCredentialMetadata) -> None:
        with db.session() as conn:
            extra_json = json.dumps(cred.extra_config)
            conn.execute(
                """
                INSERT INTO credentials_metadata (
                    id, provider, name, model, enabled, state, cooldown_until,
                    consecutive_failures, failure_count, success_count, total_tokens_used,
                    last_used_at, last_success_at, last_error_at, last_error_message,
                    rate_limit_rpm, rate_limit_tpm, extra_config_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    provider=excluded.provider,
                    name=excluded.name,
                    model=excluded.model,
                    enabled=excluded.enabled,
                    state=excluded.state,
                    cooldown_until=excluded.cooldown_until,
                    consecutive_failures=excluded.consecutive_failures,
                    failure_count=excluded.failure_count,
                    success_count=excluded.success_count,
                    total_tokens_used=excluded.total_tokens_used,
                    last_used_at=excluded.last_used_at,
                    last_success_at=excluded.last_success_at,
                    last_error_at=excluded.last_error_at,
                    last_error_message=excluded.last_error_message,
                    rate_limit_rpm=excluded.rate_limit_rpm,
                    rate_limit_tpm=excluded.rate_limit_tpm,
                    extra_config_json=excluded.extra_config_json;
                """,
                (
                    cred.id,
                    cred.provider.value,
                    cred.name,
                    cred.model,
                    1 if cred.enabled else 0,
                    cred.state.value,
                    _to_iso(cred.cooldown_until),
                    cred.consecutive_failures,
                    cred.failure_count,
                    cred.success_count,
                    cred.total_tokens_used,
                    _to_iso(cred.last_used_at),
                    _to_iso(cred.last_success_at),
                    _to_iso(cred.last_error_at),
                    cred.last_error_message,
                    cred.rate_limit_rpm,
                    cred.rate_limit_tpm,
                    extra_json,
                ),
            )

    def get_credential(self, cred_id: str) -> Optional[ProviderCredentialMetadata]:
        conn = db.get_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM credentials_metadata WHERE id = ?", (cred_id,))
        row = c.fetchone()
        if not row:
            return None
        extra = json.loads(row["extra_config_json"]) if row["extra_config_json"] else {}
        return ProviderCredentialMetadata(
            id=row["id"],
            provider=ProviderType(row["provider"]),
            name=row["name"],
            model=row["model"],
            enabled=bool(row["enabled"]),
            state=CredentialState(row["state"]),
            cooldown_until=_from_iso(row["cooldown_until"]),
            consecutive_failures=row["consecutive_failures"],
            failure_count=row["failure_count"],
            success_count=row["success_count"],
            total_tokens_used=row["total_tokens_used"],
            last_used_at=_from_iso(row["last_used_at"]),
            last_success_at=_from_iso(row["last_success_at"]),
            last_error_at=_from_iso(row["last_error_at"]),
            last_error_message=row["last_error_message"],
            rate_limit_rpm=row["rate_limit_rpm"],
            rate_limit_tpm=row["rate_limit_tpm"],
            extra_config=extra,
        )

    def list_credentials(
        self, provider: Optional[ProviderType] = None, only_enabled: bool = False
    ) -> List[ProviderCredentialMetadata]:
        conn = db.get_connection()
        c = conn.cursor()
        query = "SELECT * FROM credentials_metadata WHERE 1=1"
        params = []
        if provider:
            query += " AND provider = ?"
            params.append(provider.value)
        if only_enabled:
            query += " AND enabled = 1"
        query += " ORDER BY created_at ASC"

        c.execute(query, tuple(params))
        credentials = []
        for row in c.fetchall():
            extra = json.loads(row["extra_config_json"]) if row["extra_config_json"] else {}
            credentials.append(
                ProviderCredentialMetadata(
                    id=row["id"],
                    provider=ProviderType(row["provider"]),
                    name=row["name"],
                    model=row["model"],
                    enabled=bool(row["enabled"]),
                    state=CredentialState(row["state"]),
                    cooldown_until=_from_iso(row["cooldown_until"]),
                    consecutive_failures=row["consecutive_failures"],
                    failure_count=row["failure_count"],
                    success_count=row["success_count"],
                    total_tokens_used=row["total_tokens_used"],
                    last_used_at=_from_iso(row["last_used_at"]),
                    last_success_at=_from_iso(row["last_success_at"]),
                    last_error_at=_from_iso(row["last_error_at"]),
                    last_error_message=row["last_error_message"],
                    rate_limit_rpm=row["rate_limit_rpm"],
                    rate_limit_tpm=row["rate_limit_tpm"],
                    extra_config=extra,
                )
            )
        return credentials

    def delete_credential(self, cred_id: str) -> None:
        with db.session() as conn:
            conn.execute("DELETE FROM credentials_metadata WHERE id = ?", (cred_id,))

    def record_usage(self, usage: UsageRecord) -> None:
        with db.session() as conn:
            conn.execute(
                """
                INSERT INTO usage_records (
                    id, credential_id, provider, model, job_id, segment_id,
                    tokens_prompt, tokens_completion, tokens_total, cost_estimate_usd, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    usage.id,
                    usage.credential_id,
                    usage.provider.value,
                    usage.model,
                    usage.job_id,
                    usage.segment_id,
                    usage.tokens_prompt,
                    usage.tokens_completion,
                    usage.tokens_total,
                    usage.cost_estimate_usd,
                    _to_iso(usage.timestamp),
                ),
            )

    def get_today_usage_stats(self) -> dict:
        conn = db.get_connection()
        c = conn.cursor()
        c.execute(
            """
            SELECT
                count(*) as total_requests,
                sum(tokens_total) as total_tokens,
                sum(cost_estimate_usd) as total_cost
            FROM usage_records
            WHERE date(timestamp) = date('now');
            """
        )
        row = c.fetchone()
        return {
            "total_requests": row["total_requests"] if row and row["total_requests"] else 0,
            "total_tokens": row["total_tokens"] if row and row["total_tokens"] else 0,
            "total_cost": row["total_cost"] if row and row["total_cost"] else 0.0,
        }
