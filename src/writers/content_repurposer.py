"""Content repurposer: transforms content across formats and platforms."""

from __future__ import annotations

from typing import Optional

from src.api.llm import LLMClient, load_skill, load_style_samples, load_context, load_system_prompt


class ContentRepurposer:
    """Repurposes content across formats using content-repurposer-sms skill."""

    def __init__(self, llm: LLMClient, skills_dir: str = "./skills", config: Optional[dict] = None):
        self.llm = llm
        self.skill = load_skill("content-repurposer-sms", skills_dir)
        self.config = config

    def repurpose(
        self,
        source_content: str,
        target_platforms: Optional[list[str]] = None,
        target_formats: Optional[list[str]] = None,
        style_samples: str = "",
        context: str = "",
    ) -> str:
        """Repurpose a piece of content for other platforms/formats.

        Args:
            source_content: Original content to transform
            target_platforms: List of platforms to adapt for
            target_formats: Desired output formats (post, carousel, thread, etc.)
            style_samples: Author style examples
            context: Social media context
        """
        if target_platforms is None:
            target_platforms = ["telegram", "instagram", "threads"]
        if target_formats is None:
            target_formats = ["post", "carousel"]

        user_msg = f"""Переработай этот контент для нескольких платформ и форматов.

Исходный контент:
{source_content}

Целевые платформы: {', '.join(target_platforms)}
Целевые форматы: {', '.join(target_formats)}

Для каждого сочетания платформа+формат создай готовый контент."""

        ctx = ""
        if context:
            ctx += context + "\n\n"
        if style_samples:
            ctx += "## Примеры стиля автора\n\n" + style_samples

        return self.llm.chat_with_skill(
            skill_prompt=self.skill,
            user_message=user_msg,
            context=ctx,
        )
