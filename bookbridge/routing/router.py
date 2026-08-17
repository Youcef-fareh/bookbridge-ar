"""Central Translation Router with Multi-Key & Multi-Provider Failover."""

import asyncio
from datetime import datetime
import logging
from typing import Dict, List, Optional
from bookbridge.config.constants import CredentialState, ProviderType
from bookbridge.database.repositories.credential_repo import CredentialRepository
from bookbridge.models.job import TranslationResult
from bookbridge.models.provider import ProviderCredentialMetadata, UsageRecord
from bookbridge.models.style import StylePromptConfig
from bookbridge.providers.base import TranslationProvider
from bookbridge.providers.gemini import GeminiProvider
from bookbridge.providers.groq import GroqProvider
from bookbridge.providers.orcarouter import OrCarRouterProvider
from bookbridge.providers.mock import MockProvider
from bookbridge.routing.state_machine import CredentialStateMachine
from bookbridge.security.keyring_manager import keyring_manager

logger = logging.getLogger(__name__)


class TranslationRouter:
    def __init__(self, credential_repo: Optional[CredentialRepository] = None):
        self.credential_repo = credential_repo or CredentialRepository()
        self._providers: Dict[ProviderType, TranslationProvider] = {
            ProviderType.GEMINI: GeminiProvider(),
            ProviderType.GROQ: GroqProvider(),
            ProviderType.ORCAROUTER: OrCarRouterProvider(),
            ProviderType.MOCK: MockProvider(),
        }

    def register_provider(self, provider_type: ProviderType, provider: TranslationProvider) -> None:
        self._providers[provider_type] = provider

    def get_provider_instance(self, provider_type: ProviderType) -> Optional[TranslationProvider]:
        return self._providers.get(provider_type)

    def get_candidate_credentials(
        self, preferred_provider: Optional[ProviderType] = None
    ) -> List[ProviderCredentialMetadata]:
        """Fetch all enabled credentials, recovering expired cooldowns and ordering by health."""
        all_creds = self.credential_repo.list_credentials(only_enabled=True)
        
        # Check and recover cooldowns
        for c in all_creds:
            CredentialStateMachine.check_and_recover_cooldown(c)
            self.credential_repo.save_credential_metadata(c)

        # Filter to available
        available = [c for c in all_creds if c.is_available]
        
        # Log available credentials for debugging
        logger.info(f"Found {len(available)} available credential(s) out of {len(all_creds)} total")
        for c in available:
            secret_exists = keyring_manager.get_secret(c.id) is not None
            logger.debug(f"Credential: {c.name} ({c.provider.value}), Secret stored: {secret_exists}")

        # Prioritize matching preferred provider, then lowest consecutive failures, then lowest usage
        def sort_key(c: ProviderCredentialMetadata):
            is_preferred = 0 if (preferred_provider and c.provider == preferred_provider) else 1
            return (is_preferred, c.consecutive_failures, c.failure_count, c.total_tokens_used)

        return sorted(available, key=sort_key)

    async def translate_with_failover(
        self,
        text: str,
        context_before: str,
        context_after: str,
        style_config: StylePromptConfig,
        preferred_provider: Optional[ProviderType] = None,
        source_lang: str = "en",
        target_lang: str = "ar",
        job_id: Optional[str] = None,
        segment_id: Optional[str] = None,
    ) -> TranslationResult:
        """
        Executes translation, automatically failing over to next healthy credential
        or provider if a rate-limit (429) or transient error occurs.
        """
        candidates = self.get_candidate_credentials(preferred_provider)
        if not candidates:
            return TranslationResult(
                success=False,
                source_text=text,
                error="No active API credentials available. Please configure an API key in the Keys tab.",
                retryable=False,
            )

        last_error = ""
        for cred in candidates:
            provider = self.get_provider_instance(cred.provider)
            if not provider:
                logger.warning(f"No provider instance for {cred.provider.value}")
                continue

            secret_key = keyring_manager.get_secret(cred.id)
            if not secret_key:
                logger.error(
                    f"Secret key missing in vault for credential '{cred.name}' (ID: {cred.id}). "
                    f"The API key may not have been saved properly. "
                    f"Please delete and re-add the credential in the API Credentials tab."
                )
                CredentialStateMachine.mark_auth_error(cred, "Secret key not found in secure storage.")
                self.credential_repo.save_credential_metadata(cred)
                continue

            logger.info(f"Attempting translation via {cred.provider.value} (Key: '{cred.name}', Model: '{cred.model}')")
            result = await provider.translate(
                text=text,
                context_before=context_before,
                context_after=context_after,
                style_config=style_config,
                credential=cred,
                secret_key=secret_key,
                source_lang=source_lang,
                target_lang=target_lang,
            )

            if result.success:
                logger.info(f"Translation successful with {cred.provider.value} key '{cred.name}'")
                CredentialStateMachine.mark_success(cred, result.tokens_used)
                self.credential_repo.save_credential_metadata(cred)
                
                # Record usage statistics
                self.credential_repo.record_usage(
                    UsageRecord(
                        credential_id=cred.id,
                        provider=cred.provider,
                        model=cred.model,
                        job_id=job_id,
                        segment_id=segment_id,
                        tokens_total=result.tokens_used,
                    )
                )
                return result

            # Handle error and update state machine
            last_error = result.error or "Unknown provider error"
            if "429" in last_error or "Rate Limit" in last_error or "Quota" in last_error:
                logger.warning(f"Rate limit hit on credential '{cred.name}'")
                CredentialStateMachine.mark_rate_limited(cred, last_error)
            elif "401" in last_error or "403" in last_error or "Invalid" in last_error or "Unauthorized" in last_error:
                logger.warning(f"Authentication error on credential '{cred.name}': {last_error}")
                CredentialStateMachine.mark_auth_error(cred, last_error)
            else:
                logger.warning(f"Transient error on credential '{cred.name}': {last_error}")
                CredentialStateMachine.mark_temporary_error(cred, last_error)

            self.credential_repo.save_credential_metadata(cred)
            logger.warning(f"Failover: Credential '{cred.name}' failed ({last_error}). Trying next credential...")
            await asyncio.sleep(0.5)

        return TranslationResult(
            success=False,
            source_text=text,
            error=f"All available AI credentials failed. Last error: {last_error}",
            retryable=True,
        )


# Global router singleton
router = TranslationRouter()
