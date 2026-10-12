"""User-configured OpenAI-compatible and Gemini-compatible provider adapter."""

from typing import List
import httpx
from bookbridge.models.job import TranslationResult
from bookbridge.models.provider import ProviderCredentialMetadata
from bookbridge.models.provider_config import ProviderConfig
from bookbridge.models.style import StylePromptConfig
from bookbridge.providers.base import TranslationProvider


class GenericProvider(TranslationProvider):
    def __init__(self, config: ProviderConfig):
        self.config = config
        self.BASE_URL = config.base_url.rstrip("/")

    def _gemini_url(self, model: str) -> str:
        base_url = self.BASE_URL
        if not base_url.endswith("/v1beta/models"):
            base_url = f"{base_url}/v1beta/models"
        return f"{base_url}/{model}:generateContent"

    def get_supported_models(self) -> List[str]:
        return list(self.config.models)

    async def translate(self, text, context_before, context_after, style_config,
                        credential, secret_key, source_lang="en", target_lang="ar"):
        system = f"{style_config.system_prompt}\n\n{style_config.guidelines}\nTranslate only into {target_lang}. Output ONLY the translation, exactly once. Do not add introductions, explanations, notes, summaries, repetition, or conversation. Preserve protected tokens and paragraph breaks."
        prompt = f"[CONTEXT BEFORE]\n{context_before}\n[/CONTEXT BEFORE]\n[TRANSLATE]\n{text}\n[/TRANSLATE]\n[CONTEXT AFTER]\n{context_after}\n[/CONTEXT AFTER]"
        try:
            async with httpx.AsyncClient(timeout=40.0) as client:
                if self.config.protocol == "gemini":
                    response = await client.post(
                        self._gemini_url(credential.model),
                        headers={"x-goog-api-key": secret_key},
                        json={"system_instruction": {"parts": [{"text": system}]}, "contents": [{"role": "user", "parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.3, "maxOutputTokens": 4096}},
                    )
                    try:
                        data = response.json()
                    except ValueError:
                        return TranslationResult(success=False, source_text=text, error=f"Provider HTTP {response.status_code}: non-JSON response", retryable=response.status_code >= 500)
                    translated = "".join(p.get("text", "") for p in data.get("candidates", [{}])[0].get("content", {}).get("parts", [])).strip()
                else:
                    response = await client.post(
                        self.BASE_URL,
                        headers={"Authorization": f"Bearer {secret_key}", "Content-Type": "application/json"},
                        json={"model": credential.model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}], "temperature": 0.3},
                    )
                    try:
                        data = response.json()
                    except ValueError:
                        return TranslationResult(success=False, source_text=text, error=f"Provider HTTP {response.status_code}: non-JSON response", retryable=response.status_code >= 500)
                    translated = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            if response.status_code != 200 or not translated:
                return TranslationResult(success=False, source_text=text, error=f"Provider HTTP {response.status_code}", retryable=response.status_code >= 500)
            return TranslationResult(success=True, translated_text=translated, source_text=text, provider=self.config.id, model=credential.model)
        except Exception as exc:
            return TranslationResult(success=False, source_text=text, error=str(exc), retryable=True)

    async def validate_key(self, credential: ProviderCredentialMetadata, secret_key: str) -> bool:
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                if self.config.protocol == "gemini":
                    url = self._gemini_url(credential.model or self.config.models[0])
                    response = await client.get(url, params={"key": secret_key}, timeout=10.0)
                    return response.status_code == 200
                response = await client.get(
                    self.BASE_URL,
                    headers={"Authorization": f"Bearer {secret_key}"},
                    timeout=10.0,
                )
                return response.status_code == 200
            except Exception:
                return False
