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
from bookbridge.providers.tokenrouter import TokenRouterProvider
from bookbridge.providers.mock import MockProvider
from bookbridge.providers.generic import GenericProvider
from bookbridge.models.provider_config import ProviderConfig
from bookbridge.config.settings import settings
from bookbridge.routing.limiter import RateLimiter, rate_limiter
from bookbridge.routing.state_machine import CredentialStateMachine
from bookbridge.security.keyring_manager import keyring_manager

logger = logging.getLogger(__name__)


class TranslationRouter:
    def __init__(
        self,
        credential_repo: Optional[CredentialRepository] = None,
        limiter: Optional[RateLimiter] = None,
    ):
        self.credential_repo = credential_repo or CredentialRepository()
        self.rate_limiter = limiter or rate_limiter
        self._providers: Dict[ProviderType, TranslationProvider] = {
            ProviderType.GEMINI: GeminiProvider(),
            ProviderType.GROQ: GroqProvider(),
            ProviderType.ORCAROUTER: OrCarRouterProvider(),
            ProviderType.TOKENROUTER: TokenRouterProvider(),
            ProviderType.MOCK: MockProvider(),
        }

    def register_provider(self, provider_type: ProviderType, provider: TranslationProvider) -> None:
        self._providers[provider_type] = provider

    def get_provider_instance(self, provider_type: ProviderType) -> Optional[TranslationProvider]:
        return self._providers.get(provider_type)

    def get_provider_for_credential(self, credential: ProviderCredentialMetadata) -> Optional[TranslationProvider]:
        if credential.provider == ProviderType.CUSTOM:
            provider_id = credential.extra_config.get("provider_id")
            config = next((ProviderConfig(**row) for row in settings.provider_configs if row.get("id") == provider_id), None)
            return GenericProvider(config) if config else None
        return self.get_provider_instance(credential.provider)

    def get_candidate_credentials(
        self, preferred_provider: Optional[ProviderType] = None, estimated_tokens: int = 500
    ) -> List[ProviderCredentialMetadata]:
        """Return enabled credentials ordered by health and capacity.

        Cooldown recovery is intentionally deferred to the failover loop so
        that *reading* credentials has no database write side-effects.
        """
        all_creds = self.credential_repo.list_credentials(only_enabled=True)

        # Only keep credentials that are not permanently disabled
        available = [c for c in all_creds if c.is_available or c.state in (CredentialState.RATE_LIMITED, CredentialState.COOLDOWN)]

        if len(available) < len(all_creds):
            for cred in all_creds:
                if not cred.is_available and cred.state not in (CredentialState.RATE_LIMITED, CredentialState.COOLDOWN):
                    logger.warning(
                        "Credential '%s' is unavailable: state=%s, enabled=%s, reason=%s",
                        cred.name, cred.state.value, cred.enabled,
                        cred.last_error_message or "none",
                    )

        def sort_key(c: ProviderCredentialMetadata):
            is_pref = False
            if preferred_provider:
                if isinstance(preferred_provider, ProviderType):
                    is_pref = (c.provider == preferred_provider)
                else:
                    pref_str = str(preferred_provider).lower()
                    is_pref = (
                        c.provider.value.lower() == pref_str
                        or str(c.extra_config.get("provider_id", "")).lower() == pref_str
                    )
            is_preferred = 0 if is_pref else 1
            can_go, wait_s, _ = self.rate_limiter.check_capacity(c, estimated_tokens)
            has_capacity = 0 if can_go else (1 if wait_s < 30.0 else 2)
            return (is_preferred, has_capacity, c.consecutive_failures, c.failure_count, c.total_tokens_used)

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
        cancel_check=None,
    ) -> TranslationResult:
        """
        Executes translation, strictly respecting RPM, TPM, and RPD rate limits
        and automatically failing over to next healthy credential or provider.
        """
        estimated_tokens = self.rate_limiter.estimate_tokens(text)
        candidates = self.get_candidate_credentials(preferred_provider, estimated_tokens)
        if not candidates:
            return TranslationResult(
                success=False,
                source_text=text,
                error="No active API credentials available or all daily quotas reached. Please configure an API key in the Keys tab.",
                retryable=False,
            )

        last_error = ""
        for cred in candidates:
            if cancel_check and cancel_check():
                return TranslationResult(success=False, cancelled=True, source_text=text, error="Translation cancelled by user.", retryable=False)

            # Lazy cooldown recovery: only check+recover when we are about to use a credential
            if cred.state in (CredentialState.RATE_LIMITED, CredentialState.COOLDOWN):
                CredentialStateMachine.check_and_recover_cooldown(cred)
                self.credential_repo.save_credential_metadata(cred)
                if not cred.is_available:
                    logger.debug(f"Credential '{cred.name}' still in cooldown, skipping.")
                    continue

            provider = self.get_provider_for_credential(cred)
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

            # Strict Rate Limiting: acquire token/request budget before making API call
            acquired = await self.rate_limiter.acquire(
                cred,
                estimated_tokens=estimated_tokens,
                max_wait_seconds=65.0,
                cancel_check=cancel_check,
            )
            if not acquired:
                if cancel_check and cancel_check():
                    return TranslationResult(success=False, source_text=text, error="Translation cancelled by user.", retryable=False)
                logger.warning(
                    f"Could not acquire rate limit slot for '{cred.name}' ({cred.provider.value}). Failing over to next key..."
                )
                continue

            logger.info(
                f"Attempting translation via {cred.provider.value} (Key: '{cred.name}', Model: '{cred.model}', "
                f"RPM limit: {cred.effective_rpm}, TPM limit: {cred.effective_tpm})"
            )
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

            if cancel_check and cancel_check():
                return TranslationResult(success=False, cancelled=True, source_text=text, error="Translation cancelled by user.", retryable=False)

            if result.success:
                logger.info(f"Translation successful with {cred.provider.value} key '{cred.name}'")
                self.rate_limiter.record_usage(cred, result.tokens_used)
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
                logger.warning(f"Rate limit hit on credential '{cred.name}': {last_error}")
                CredentialStateMachine.mark_rate_limited(cred, last_error)
            elif "401" in last_error or "403" in last_error or "Invalid" in last_error or "Unauthorized" in last_error:
                logger.warning(f"Authentication error on credential '{cred.name}': {last_error}")
                CredentialStateMachine.mark_auth_error(cred, last_error)
            else:
                logger.warning(f"Transient error on credential '{cred.name}': {last_error}")
                CredentialStateMachine.mark_temporary_error(cred, last_error)

            self.credential_repo.save_credential_metadata(cred)
            logger.warning(f"Failover: Credential '{cred.name}' failed ({last_error}). Trying next credential...")
            await asyncio.sleep(0.1)  # Minimal inter-credential delay; user cooldown is applied by JobRunner

        return TranslationResult(
            success=False,
            source_text=text,
            error=f"All available AI credentials failed. Last error: {last_error}",
            retryable=True,
        )
