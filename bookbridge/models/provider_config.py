"""User-managed translation provider configuration."""

from typing import List
import uuid
from pydantic import BaseModel, Field


class ProviderConfig(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    base_url: str
    protocol: str = "openai"
    models: List[str] = Field(default_factory=list)
    rate_limit_rpm: int = 20
    rate_limit_tpm: int = 60000
    rate_limit_rpd: int = 1000
    enabled: bool = True
