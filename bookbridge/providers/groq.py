"""Groq AI Provider implementation using high-speed Llama models."""

import logging
from typing import List
import httpx
from bookbridge.config.constants import ProviderType
from bookbridge.models.job import TranslationResult
from bookbridge.models.provider import ProviderCredentialMetadata
from bookbridge.models.style import StylePromptConfig
from bookbridge.providers.base import TranslationProvider

logger = logging.getLogger(__name__)


class GroqProvider(TranslationProvider):
    BASE_URL = "https://api.groq.com/openai/v1/chat/completions"

    def get_supported_models(self) -> List[str]:
        return [
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant",
            "mixtral-8x7b-32768",
        ]

    def _build_system_prompt(
        self, style_config: StylePromptConfig, source_lang: str, target_lang: str
    ) -> str:
        return (
            f"{style_config.system_prompt}\n\n"
            f"STYLE GUIDELINES:\n{style_config.guidelines}\n\n"
            f"SOURCE LANGUAGE: {source_lang.upper()}\n"
            f"TARGET LANGUAGE: {target_lang.upper()}\n\n"
            "CRITICAL RULES:\n"
            "1. Output ONLY the translated Arabic text.\n"
            "2. Preserve all protected tokens like <NB_TERM_001>, <NB_TERM_002>, etc. exactly as they appear.\n"
            "3. Maintain original paragraph breaks and line spacing.\n"
            "4. Do not omit or summarize any text."
        )

    def _build_user_prompt(self, text: str, context_before: str, context_after: str) -> str:
        prompt_parts = []
        if context_before.strip():
            prompt_parts.append(f"[CONTEXT BEFORE]\n{context_before.strip()}\n[/CONTEXT BEFORE]")
        prompt_parts.append(f"[TRANSLATE THIS TEXT]\n{text}\n[/TRANSLATE THIS TEXT]")
        if context_after.strip():
            prompt_parts.append(f"[CONTEXT AFTER]\n{context_after.strip()}\n[/CONTEXT AFTER]")
        prompt_parts.append("Translate only the section inside [TRANSLATE THIS TEXT] into Arabic:")
        return "\n\n".join(prompt_parts)

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
        model = credential.model or "llama-3.3-70b-versatile"
        headers = {
            "Authorization": f"Bearer {secret_key}",
            "Content-Type": "application/json",
        }
        system_content = self._build_system_prompt(style_config, source_lang, target_lang)
        user_content = self._build_user_prompt(text, context_before, context_after)

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_content},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0.3,
            "max_tokens": 4096,
        }

        async with httpx.AsyncClient(timeout=35.0) as client:
            try:
                response = await client.post(self.BASE_URL, headers=headers, json=payload)
                status = response.status_code

                if status == 200:
                    data = response.json()
                    choices = data.get("choices", [])
                    if choices:
                        translated_text = choices[0].get("message", {}).get("content", "").strip()
                        if translated_text.startswith("```") and translated_text.endswith("```"):
                            lines = translated_text.splitlines()
                            if len(lines) >= 2:
                                translated_text = "\n".join(lines[1:-1]).strip()

                        usage = data.get("usage", {})
                        total_tokens = usage.get("total_tokens", 0)

                        return TranslationResult(
                            success=True,
                            translated_text=translated_text,
                            source_text=text,
                            provider=ProviderType.GROQ.value,
                            model=model,
                            credential_id=credential.id,
                            tokens_used=total_tokens,
                        )
                    else:
                        return TranslationResult(
                            success=False,
                            source_text=text,
                            provider=ProviderType.GROQ.value,
                            model=model,
                            credential_id=credential.id,
                            error="Groq returned empty choices.",
                            retryable=False,
                        )

                elif status == 429:
                    return TranslationResult(
                        success=False,
                        source_text=text,
                        provider=ProviderType.GROQ.value,
                        model=model,
                        credential_id=credential.id,
                        error="HTTP 429: Groq Rate Limit Exceeded.",
                        retryable=True,
                    )
                elif status in (401, 403):
                    return TranslationResult(
                        success=False,
                        source_text=text,
                        provider=ProviderType.GROQ.value,
                        model=model,
                        credential_id=credential.id,
                        error=f"HTTP {status}: Invalid Groq API Key.",
                        retryable=False,
                    )
                else:
                    return TranslationResult(
                        success=False,
                        source_text=text,
                        provider=ProviderType.GROQ.value,
                        model=model,
                        credential_id=credential.id,
                        error=f"HTTP {status}: {response.text[:200]}",
                        retryable=(status >= 500),
                    )

            except httpx.TimeoutException:
                return TranslationResult(
                    success=False,
                    source_text=text,
                    provider=ProviderType.GROQ.value,
                    model=model,
                    credential_id=credential.id,
                    error="Groq Request Timeout.",
                    retryable=True,
                )
            except Exception as ex:
                return TranslationResult(
                    success=False,
                    source_text=text,
                    provider=ProviderType.GROQ.value,
                    model=model,
                    credential_id=credential.id,
                    error=f"Groq Client Error: {str(ex)}",
                    retryable=True,
                )

    async def validate_key(self, credential: ProviderCredentialMetadata, secret_key: str) -> bool:
        headers = {"Authorization": f"Bearer {secret_key}"}
        payload = {
            "model": "llama-3.1-8b-instant",
            "messages": [{"role": "user", "content": "Reply with 'OK'."}],
            "max_tokens": 5,
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                res = await client.post(self.BASE_URL, headers=headers, json=payload)
                return res.status_code == 200
            except Exception:
                return False
