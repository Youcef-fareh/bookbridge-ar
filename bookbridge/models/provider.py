"""Provider credentials metadata and usage models."""

from datetime import datetime, timezone
import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from bookbridge.config.constants import CredentialState, ProviderType


class ProviderCredentialMetadata(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    provider: ProviderType = ProviderType.GEMINI
    name: str = "Primary Key"
    model: str = "gemini-2.5-flash"
    enabled: bool = True
    state: CredentialState = CredentialState.AVAILABLE
    cooldown_until: Optional[datetime] = None
    consecutive_failures: int = 0
    failure_count: int = 0
    success_count: int = 0
    total_tokens_used: int = 0
    last_used_at: Optional[datetime] = None
    last_success_at: Optional[datetime] = None
    last_error_at: Optional[datetime] = None
    last_error_message: Optional[str] = None
    rate_limit_rpm: Optional[int] = None
    rate_limit_tpm: Optional[int] = None
    extra_config: Dict[str, Any] = Field(default_factory=dict)

    @property
    def is_available(self) -> bool:
        if not self.enabled or self.state in (
            CredentialState.DISABLED,
            CredentialState.INVALID,
            CredentialState.AUTH_ERROR,
            CredentialState.ERROR,
        ):
            return False
        if self.state in (CredentialState.COOLDOWN, CredentialState.RATE_LIMITED):
            if self.cooldown_until:
                now = datetime.now(timezone.utc)
                cd = self.cooldown_until if self.cooldown_until.tzinfo else self.cooldown_until.replace(tzinfo=timezone.utc)
                if now < cd:
                    return False
            else:
                return False
        return True


class UsageRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    credential_id: str
    provider: ProviderType
    model: str
    job_id: Optional[str] = None
    segment_id: Optional[str] = None
    tokens_prompt: int = 0
    tokens_completion: int = 0
    tokens_total: int = 0
    cost_estimate_usd: float = 0.0
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
