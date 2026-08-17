"""Translation style models and prompts."""

from typing import Dict
from pydantic import BaseModel, Field
from bookbridge.config.constants import TranslationStyleType


class StylePromptConfig(BaseModel):
    style_type: TranslationStyleType = TranslationStyleType.NATURAL
    name: str = "Natural Arabic"
    description: str = "Fluent, natural contemporary Arabic phrasing suitable for general fiction."
    system_prompt: str = ""
    guidelines: str = ""
    formality: str = "standard"  # standard, literary, modern


STYLE_PRESETS: Dict[TranslationStyleType, StylePromptConfig] = {
    TranslationStyleType.NATURAL: StylePromptConfig(
        style_type=TranslationStyleType.NATURAL,
        name="Natural Arabic (العربية المعاصرة السلسة)",
        description="Fluent, idiomatic modern Arabic novel style. Balances flow and accuracy.",
        system_prompt=(
            "You are an expert literary translator specialized in translating English fiction and novels "
            "into fluent, expressive, and natural Modern Standard Arabic (فصحى معاصرة). "
            "Preserve character voice, pacing, dramatic tension, and emotional nuances."
        ),
        guidelines=(
            "- Use natural Arabic syntax and elegant phrasing (تراكيب عربية أصيلة).\n"
            "- Avoid awkward literal word-for-word translation.\n"
            "- Ensure dialogue sounds natural in spoken tone while remaining in accessible standard Arabic.\n"
            "- Strictly preserve all placeholder tokens like <NB_TERM_XXX> without modifying them.\n"
            "- Do not add commentary, notes, or extra text. Output ONLY the translated content."
        ),
    ),
    TranslationStyleType.LITERARY: StylePromptConfig(
        style_type=TranslationStyleType.LITERARY,
        name="Literary Arabic (العربية الأدبية الراقية)",
        description="High classical prose with rich vocabulary and sophisticated literary tone.",
        system_prompt=(
            "You are a master literary translator and Arabic prose stylist. Translate the English novel into "
            "rich, eloquent, and sophisticated Arabic literature (فصحى أدبية رفيعة) with evocative imagery."
        ),
        guidelines=(
            "- Employ rich classical vocabulary and majestic prose rhythms.\n"
            "- Elevate poetic descriptions and atmospheric worldbuilding.\n"
            "- Strictly preserve all placeholder tokens like <NB_TERM_XXX>.\n"
            "- Do not add notes or translator remarks."
        ),
    ),
    TranslationStyleType.WEB_NOVEL: StylePromptConfig(
        style_type=TranslationStyleType.WEB_NOVEL,
        name="Web Novel Arabic (روايات الويب والأنظمة)",
        description="Fast-paced, dynamic style optimized for Xianxia, LitRPG, cultivation, and system novels.",
        system_prompt=(
            "You are a specialized translator for Asian web novels (Xianxia, Xuanhuan, LitRPG, Wuxia, and System novels) "
            "into Arabic. Deliver crisp action scenes, sharp cultivation levels, and immersive game/system notifications."
        ),
        guidelines=(
            "- Keep status panels, system prompts, skill activations, and realm names clear and impactful.\n"
            "- Maintain fast action pacing and martial arts terminology.\n"
            "- Strictly preserve all placeholder tokens like <NB_TERM_XXX>.\n"
            "- Output ONLY the translated text."
        ),
    ),
    TranslationStyleType.LITERAL: StylePromptConfig(
        style_type=TranslationStyleType.LITERAL,
        name="Literal Arabic (ترجمة دقيقة مطابقة)",
        description="Close fidelity to the English source structure and phrasing.",
        system_prompt=(
            "You are a precise translator prioritizing direct faithfulness to the original sentence structure and wording."
        ),
        guidelines=(
            "- Maintain direct correspondence with source clauses and terminology.\n"
            "- Strictly preserve all placeholder tokens like <NB_TERM_XXX>.\n"
            "- Output ONLY the translated text."
        ),
    ),
}
