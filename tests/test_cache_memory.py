"""Tests for Deterministic Request Cache and Translation Memory."""

import pytest
from bookbridge.config.constants import ProviderType, TranslationStyleType
from bookbridge.database.repositories.credential_repo import CredentialRepository
from bookbridge.database.repositories.memory_repo import MemoryRepository
from bookbridge.engine.translator import TranslationPipeline
from bookbridge.models.glossary import GlossaryProfile
from bookbridge.models.job import Segment
from bookbridge.models.provider import ProviderCredentialMetadata
from bookbridge.providers.mock import MockProvider
from bookbridge.routing.router import TranslationRouter
from bookbridge.security.keyring_manager import keyring_manager


@pytest.mark.asyncio
async def test_cache_and_memory_reusability():
    cred_repo = CredentialRepository()
    memory_repo = MemoryRepository()
    router = TranslationRouter(cred_repo)

    mock_provider = MockProvider()
    router.register_provider(ProviderType.MOCK, mock_provider)

    # Save mock credential
    cred = ProviderCredentialMetadata(
        id="cred_cache_test",
        provider=ProviderType.MOCK,
        name="Cache Key",
    )
    cred_repo.save_credential_metadata(cred)
    keyring_manager.save_secret(cred.id, "secret_123")

    pipeline = TranslationPipeline(router=router, memory_repo=memory_repo)

    seg = Segment(
        job_id="job_c1",
        chapter_id="ch_1",
        source_text="The water flowed through the valley.",
    )

    profile = GlossaryProfile()

    # Call 1: Brand new translation (should call provider)
    initial_calls = mock_provider.call_count
    res1 = await pipeline.translate_segment(
        segment=seg,
        context_before="",
        context_after="",
        glossary_profile=profile,
        style_type=TranslationStyleType.NATURAL,
    )
    assert res1.success is True
    assert res1.cached is False
    assert mock_provider.call_count == initial_calls + 1

    # Call 2: Exact duplicate request (should hit Request Cache without calling provider)
    res2 = await pipeline.translate_segment(
        segment=seg,
        context_before="",
        context_after="",
        glossary_profile=profile,
        style_type=TranslationStyleType.NATURAL,
    )
    assert res2.success is True
    assert res2.cached is True
    # Call count must NOT have increased!
    assert mock_provider.call_count == initial_calls + 1
