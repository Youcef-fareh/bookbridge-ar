"""Tests for Translation Router, Credential State Machine, and Failover."""

import pytest
from bookbridge.config.constants import CredentialState, ProviderType, TranslationStyleType
from bookbridge.database.repositories.credential_repo import CredentialRepository
from bookbridge.config.constants import ProviderType
from bookbridge.models.provider import ProviderCredentialMetadata
from bookbridge.models.style import STYLE_PRESETS
from bookbridge.providers.groq import GroqProvider
from bookbridge.providers.mock import MockProvider
from bookbridge.providers.orcarouter import OrCarRouterProvider
from bookbridge.routing.router import TranslationRouter
from bookbridge.security.keyring_manager import keyring_manager


@pytest.mark.asyncio
async def test_router_failover_on_429():
    cred_repo = CredentialRepository()
    router = TranslationRouter(cred_repo)

    # Register mock providers
    failing_mock = MockProvider(failure_mode="rate_limit_429")
    success_mock = MockProvider(failure_mode=None)
    router.register_provider(ProviderType.MOCK, failing_mock)

    # Create Credential A (will 429)
    cred_a = ProviderCredentialMetadata(
        id="cred_test_a",
        provider=ProviderType.MOCK,
        name="Mock Key A",
    )
    cred_repo.save_credential_metadata(cred_a)
    keyring_manager.save_secret(cred_a.id, "fake_key_a")

    # Create Credential B (will succeed)
    cred_b = ProviderCredentialMetadata(
        id="cred_test_b",
        provider=ProviderType.MOCK,
        name="Mock Key B",
    )
    cred_repo.save_credential_metadata(cred_b)
    keyring_manager.save_secret(cred_b.id, "fake_key_b")

    # First attempt: Router tries A, gets 429, marks A as RATE_LIMITED, fails over to B
    # To simulate B succeeding, let router switch instance or let second key succeed:
    call_counts = 0

    class AlternatingMock(MockProvider):
        async def translate(self, *args, **kwargs):
            nonlocal call_counts
            call_counts += 1
            cred = kwargs.get("credential")
            if cred.id == "cred_test_a":
                return await failing_mock.translate(*args, **kwargs)
            return await success_mock.translate(*args, **kwargs)

    router.register_provider(ProviderType.MOCK, AlternatingMock())

    result = await router.translate_with_failover(
        text="Chapter 1: The Beginning",
        context_before="",
        context_after="",
        style_config=STYLE_PRESETS[TranslationStyleType.NATURAL],
    )

    assert result.success is True
    assert "الفصل" in result.translated_text

    # Verify Credential A was put into RATE_LIMITED state
    updated_a = cred_repo.get_credential("cred_test_a")
    assert updated_a.state == CredentialState.RATE_LIMITED
    assert updated_a.cooldown_until is not None

    # Verify Credential B succeeded
    updated_b = cred_repo.get_credential("cred_test_b")
    assert updated_b.state == CredentialState.AVAILABLE
    assert updated_b.success_count >= 1


def test_groq_model_alias_and_supported_models():
    provider = GroqProvider()

    assert "llama-3.3-70b-versatile" in provider.get_supported_models()
    assert "llama-3.1-70b-versatile" in provider.get_supported_models()
    assert "meta-llama/llama-4-scout-17b-16e-instruct" in provider.get_supported_models()

    assert provider.resolve_model_name("groq/llama-3.1-8b-instant") == "llama-3.1-8b-instant"
    assert provider.resolve_model_name("llama-3.1-70b-versatile") == "llama-3.1-70b-versatile"
    assert provider.resolve_model_name("") == "llama-3.3-70b-versatile"


def test_orcarouter_provider_registration_and_supported_models():
    provider = OrCarRouterProvider()
    assert ProviderType.ORCAROUTER.value == "orcarouter"
    assert "qwen/qwen3.8-27b-free" in provider.get_supported_models()
    assert provider.resolve_model_name("qwen/qwen3.8-27b-free") == "qwen/qwen3.8-27b-free"
    assert provider.resolve_model_name("") == "qwen/qwen3.8-27b-free"
