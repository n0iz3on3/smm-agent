"""Hook writer: generates attention-grabbing hooks using hook-writer-sms skill."""

from __future__ import annotations

from typing import Optional

from src.api.llm import LLMClient, load_skill, load_style_samples, load_context, load_system_prompt


class HookWriter:
    """Writes hooks using the hook-writer-sms skill."""

    def __init__(self, llm: LLMClient, skills_dir: str = "./skills", config: Optional[dict] = None):
        self.llm = llm
        self.skill = load_skill("hook-writer-sms", skills_dir)
        self.config = config

    def write_hooks(
        self,
        topic: str,
        platform: str = "telegram",
        count: int = 5,
        patterns: Optional[list[str]] = None,
        style_samples: str = "",
        context: str = "",
    ) -> str:
        """Generate multiple hook variants for a topic.

        Args:
            topic: What the hook is about
            platform: telegram | instagram | threads
            count: Number of variants
            patterns: Optional list of hook patterns to use
                (contrarian, question, story, statistic, list, bold, empathy, before_after, confession)
            style_samples: Author style examples
            context: Social media context
        """
        user_msg = f"""Сгенерируй {count} вариантов хуков на тему: {topic}

Платформа: {platform}
{f'Паттерны: {", ".join(patterns)}' if patterns else 'Используй разные паттерны из библиотеки'}

Для каждого хука укажи:
- Текст хука
- Паттерн
- Почему сработает"""

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
