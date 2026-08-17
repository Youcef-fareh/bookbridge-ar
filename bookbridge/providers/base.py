"""Base Translation Provider Abstract Interface."""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from bookbridge.models.job import TranslationResult
from bookbridge.models.provider import ProviderCredentialMetadata
from bookbridge.models.style import StylePromptConfig


class TranslationProvider(ABC):
    @abstractmethod
    async def translate(
        self,
        text: str,
        context_before: str,
        context_after: str,
        style_config: StylePromptConfig,
        credential: ProviderCredentialMetadata,
        secret_key: str,
        source_lang: str = "en",
        target_lang: str = "ar",
    ) -> TranslationResult:
        """Execute translation request through the AI provider."""
        pass

    @abstractmethod
    async def validate_key(self, credential: ProviderCredentialMetadata, secret_key: str) -> bool:
        """Validate whether the API key is active and functional."""
        pass

    @abstractmethod
    def get_supported_models(self) -> List[str]:
        """List of default/recommended models for this provider."""
        pass
