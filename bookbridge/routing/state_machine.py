"""Credential State Machine & Health Tracking."""

from datetime import datetime, timedelta, timezone
import logging
from typing import Optional
from bookbridge.config.constants import CredentialState, DEFAULT_COOLDOWN_SECONDS
from bookbridge.models.provider import ProviderCredentialMetadata

logger = logging.getLogger(__name__)


class CredentialStateMachine:
    @staticmethod
    def mark_success(cred: ProviderCredentialMetadata, tokens_used: int = 0) -> None:
        cred.state = CredentialState.AVAILABLE
        cred.consecutive_failures = 0
        cred.success_count += 1
        cred.total_tokens_used += tokens_used
        cred.last_success_at = datetime.now(timezone.utc)
        cred.last_used_at = datetime.now(timezone.utc)
        cred.cooldown_until = None
        cred.last_error_message = None

    @staticmethod
    def mark_rate_limited(
        cred: ProviderCredentialMetadata,
        error_msg: str,
        cooldown_seconds: int = DEFAULT_COOLDOWN_SECONDS,
    ) -> None:
        cred.state = CredentialState.RATE_LIMITED
        cred.consecutive_failures += 1
        cred.failure_count += 1
        cred.last_error_at = datetime.now(timezone.utc)
        cred.last_used_at = datetime.now(timezone.utc)
        cred.last_error_message = error_msg
        # Exponential cooldown based on consecutive failures: cooldown * 1.5 ^ (failures - 1)
        multiplier = 1.5 ** min(cred.consecutive_failures - 1, 4)
        effective_cooldown = int(cooldown_seconds * multiplier)
        cred.cooldown_until = datetime.now(timezone.utc) + timedelta(seconds=effective_cooldown)
        logger.warning(
            f"Credential '{cred.name}' ({cred.provider.value}) rate-limited. Cooldown for {effective_cooldown}s."
        )

    @staticmethod
    def mark_auth_error(cred: ProviderCredentialMetadata, error_msg: str) -> None:
        cred.state = CredentialState.AUTH_ERROR
        cred.consecutive_failures += 1
        cred.failure_count += 1
        cred.last_error_at = datetime.now(timezone.utc)
        cred.last_used_at = datetime.now(timezone.utc)
        cred.last_error_message = error_msg
        logger.error(f"Credential '{cred.name}' failed authentication: {error_msg}")

    @staticmethod
    def mark_temporary_error(cred: ProviderCredentialMetadata, error_msg: str) -> None:
        cred.consecutive_failures += 1
        cred.failure_count += 1
        cred.last_error_at = datetime.now(timezone.utc)
        cred.last_used_at = datetime.now(timezone.utc)
        cred.last_error_message = error_msg
        if cred.consecutive_failures >= 3:
            cred.state = CredentialState.COOLDOWN
            cred.cooldown_until = datetime.now(timezone.utc) + timedelta(seconds=30)
            logger.warning(f"Credential '{cred.name}' has 3 consecutive errors. Putting in 30s cooldown.")
        else:
            cred.state = CredentialState.ERROR

    @staticmethod
    def check_and_recover_cooldown(cred: ProviderCredentialMetadata) -> None:
        """Check if cooldown expired and restore state to AVAILABLE."""
        if cred.state in (CredentialState.RATE_LIMITED, CredentialState.COOLDOWN):
            now = datetime.now(timezone.utc)
            if cred.cooldown_until:
                # Ensure timezone-aware comparison
                cd = cred.cooldown_until if cred.cooldown_until.tzinfo else cred.cooldown_until.replace(tzinfo=timezone.utc)
                if now >= cd:
                    cred.state = CredentialState.AVAILABLE
                    cred.cooldown_until = None
                    logger.info(f"Credential '{cred.name}' cooldown expired. Restored to AVAILABLE.")
