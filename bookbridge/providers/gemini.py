"""Google Gemini AI Provider implementation with rate-limit and error classification."""

import logging
from typing import List
import httpx
from bookbridge.config.constants import ProviderType
from bookbridge.models.job import TranslationResult
from bookbridge.models.provider import ProviderCredentialMetadata
from bookbridge.models.style import StylePromptConfig
from bookbridge.providers.base import TranslationProvider

logger = logging.getLogger(__name__)


class GeminiProvider(TranslationProvider):
    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

    def get_supported_models(self) -> List[str]:
        return [
            "gemini-3.5-flash-lite",
            "gemini-3.1-flash-lite",
            "gemini-2.5-flash",
            "gemini-1.5-flash",
            "gemini-1.5-pro",
            "gemini-2.0-flash",
        ]

    def _build_system_instructions(
        self,
        style_config: StylePromptConfig,
        source_lang: str,
        target_lang: str,
    ) -> str:
        return (
            f"{style_config.system_prompt}\n\n"
            f"STYLE GUIDELINES:\n{style_config.guidelines}\n\n"
            f"SOURCE LANGUAGE: {source_lang.upper()}\n"
            f"TARGET LANGUAGE: {target_lang.upper()}\n\n"
            "CRITICAL RULES:\n"
            "1. Output ONLY the translated text. Do NOT include markdown code blocks (like ```arabic), explanations, or notes.\n"
            "2. Preserve all protected tokens like <NB_TERM_001>, <NB_TERM_002>, etc. exactly as they appear.\n"
            "3. Maintain original paragraph breaks and line spacing.\n"
            "4. Do not omit any sentence or dialogue."
        )

    def _build_user_prompt(self, text: str, context_before: str, context_after: str) -> str:
        prompt_parts = []
        if context_before.strip():
            prompt_parts.append(f"--- PREVIOUS CONTEXT (DO NOT TRANSLATE) ---\n{context_before.strip()}\n--- END CONTEXT ---")
        prompt_parts.append(f"--- TEXT TO TRANSLATE (TRANSLATE THIS) ---\n{text}\n--- END TEXT ---")
        if context_after.strip():
            prompt_parts.append(f"--- UPCOMING CONTEXT (DO NOT TRANSLATE) ---\n{context_after.strip()}\n--- END CONTEXT ---")
        prompt_parts.append("Translate only the 'TEXT TO TRANSLATE' section into Arabic:")
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
        model = credential.model or "gemini-2.5-flash"
        url = f"{self.BASE_URL}/{model}:generateContent?key={secret_key}"
        system_instruction = self._build_system_instructions(style_config, source_lang, target_lang)
        user_prompt = self._build_user_prompt(text, context_before, context_after)

        payload = {
            "system_instruction": {
                "parts": [{"text": system_instruction}]
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": user_prompt}],
                }
            ],
            "generationConfig": {
                "temperature": 0.3,
                "topP": 0.95,
            },
        }

        async with httpx.AsyncClient(timeout=40.0) as client:
            try:
                response = await client.post(url, json=payload)
                status = response.status_code

                if status == 200:
                    data = response.json()
                    candidates = data.get("candidates", [])
                    if candidates and "content" in candidates[0]:
                        parts = candidates[0]["content"].get("parts", [])
                        translated_text = "".join(p.get("text", "") for p in parts).strip()
                        # Clean code block artifacts if LLM wrapped it
                        if translated_text.startswith("```") and translated_text.endswith("```"):
                            lines = translated_text.splitlines()
                            if len(lines) >= 2:
                                translated_text = "\n".join(lines[1:-1]).strip()

                        usage_meta = data.get("usageMetadata", {})
                        tokens_total = usage_meta.get("totalTokenCount", 0)

                        return TranslationResult(
                            success=True,
                            translated_text=translated_text,
                            source_text=text,
                            provider=ProviderType.GEMINI.value,
                            model=model,
                            credential_id=credential.id,
                            tokens_used=tokens_total,
                        )
                    else:
                        return TranslationResult(
                            success=False,
                            source_text=text,
                            provider=ProviderType.GEMINI.value,
                            model=model,
                            credential_id=credential.id,
                            error="Gemini returned an empty candidate list or blocked content.",
                            retryable=False,
                        )

                elif status == 429:
                    return TranslationResult(
                        success=False,
                        source_text=text,
                        provider=ProviderType.GEMINI.value,
                        model=model,
                        credential_id=credential.id,
                        error="HTTP 429: Gemini Rate Limit / Quota Exceeded.",
                        retryable=True,
                    )
                elif status in (401, 403):
                    return TranslationResult(
                        success=False,
                        source_text=text,
                        provider=ProviderType.GEMINI.value,
                        model=model,
                        credential_id=credential.id,
                        error=f"HTTP {status}: Invalid API Key or Unauthorized.",
                        retryable=False,
                    )
                else:
                    return TranslationResult(
                        success=False,
                        source_text=text,
                        provider=ProviderType.GEMINI.value,
                        model=model,
                        credential_id=credential.id,
                        error=f"HTTP {status}: {response.text[:200]}",
                        retryable=(status >= 500),
                    )

            except httpx.TimeoutException:
                return TranslationResult(
                    success=False,
                    source_text=text,
                    provider=ProviderType.GEMINI.value,
                    model=model,
                    credential_id=credential.id,
                    error="Gemini Request Timeout.",
                    retryable=True,
                )
            except Exception as ex:
                return TranslationResult(
                    success=False,
                    source_text=text,
                    provider=ProviderType.GEMINI.value,
                    model=model,
                    credential_id=credential.id,
                    error=f"Gemini Client Error: {str(ex)}",
                    retryable=True,
                )

    async def validate_key(self, credential: ProviderCredentialMetadata, secret_key: str) -> bool:
        model = credential.model or "gemini-2.5-flash"
        url = f"{self.BASE_URL}/{model}:generateContent?key={secret_key}"
        payload = {
            "contents": [{"role": "user", "parts": [{"text": "Reply with 'OK'."}]}],
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                response = await client.post(url, json=payload)
                return response.status_code == 200
            except Exception:
                return False
