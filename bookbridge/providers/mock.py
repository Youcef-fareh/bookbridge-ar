"""Mock Translation Provider for testing, offline verification, and failover simulation."""

from typing import List, Optional
from bookbridge.config.constants import ProviderType
from bookbridge.models.job import TranslationResult
from bookbridge.models.provider import ProviderCredentialMetadata
from bookbridge.models.style import StylePromptConfig
from bookbridge.providers.base import TranslationProvider


class MockProvider(TranslationProvider):
    def __init__(self, failure_mode: Optional[str] = None):
        """
        failure_mode options: None, 'rate_limit_429', 'auth_error', 'timeout'
        """
        self.failure_mode = failure_mode
        self.call_count = 0

    def get_supported_models(self) -> List[str]:
        return ["mock-model-v1"]

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
        self.call_count += 1

        if self.failure_mode == "rate_limit_429":
            return TranslationResult(
                success=False,
                source_text=text,
                provider=ProviderType.MOCK.value,
                model="mock-model-v1",
                credential_id=credential.id,
                error="HTTP 429: Mock Rate Limit Exceeded",
                retryable=True,
            )
        elif self.failure_mode == "auth_error":
            return TranslationResult(
                success=False,
                source_text=text,
                provider=ProviderType.MOCK.value,
                model="mock-model-v1",
                credential_id=credential.id,
                error="HTTP 401: Mock Authentication Failure",
                retryable=False,
            )

        # Mock translation that preserves protected tokens and translates words into sample Arabic
        # For testing, replace common words with Arabic sample text
        arabic_mock = text
        sample_replacements = {
            "The": "إن",
            "the": "الـ",
            "flowed": "تدفق",
            "through": "عبر",
            "valley": "الوادي",
            "Chapter": "الفصل",
            "Hello": "مرحبا",
            "world": "بالعالم",
        }
        for eng, ar in sample_replacements.items():
            arabic_mock = arabic_mock.replace(eng, ar)

        if not arabic_mock.strip():
            arabic_mock = "نص تجريبي مترجم."

        return TranslationResult(
            success=True,
            translated_text=arabic_mock,
            source_text=text,
            provider=ProviderType.MOCK.value,
            model="mock-model-v1",
            credential_id=credential.id,
            tokens_used=len(text.split()) + 5,
        )

    async def validate_key(self, credential: ProviderCredentialMetadata, secret_key: str) -> bool:
        return self.failure_mode != "auth_error"
