"""Post writer: generates social media posts using post-writer-sms skill."""

from __future__ import annotations

from typing import Optional

from src.api.llm import LLMClient, load_skill, load_style_samples, load_context, load_system_prompt


class PostWriter:
    """Writes platform-native posts using the post-writer-sms skill."""

    def __init__(self, llm: LLMClient, skills_dir: str = "./skills", config: Optional[dict] = None):
        self.llm = llm
        self.skill = load_skill("post-writer-sms", skills_dir)
        self.config = config

    def write_post(
        self,
        topic: str,
        platform: str = "telegram",
        content_type: str = "storytelling",
        angle: str = "",
        style_samples: str = "",
        context: str = "",
        system_prompt: str = "",
    ) -> str:
        """Generate a social media post.

        Args:
            topic: What to write about
            platform: telegram | instagram | threads
            content_type: storytelling | educational | engagement | promotional
            angle: Specific angle or CTA
            style_samples: User's style examples
            context: Social media context (voice, tone, pillars)
            system_prompt: Custom system prompt override
        """
        user_msg = f"""Напиши пост на тему: {topic}

Платформа: {platform}
Тип контента: {content_type}
{f'Угол/CTA: {angle}' if angle else ''}

Сгенерируй готовый пост, оптимизированный для этой платформы."""

        extra = system_prompt or ""
        ctx = ""
        if context:
            ctx += context + "\n\n"
        if style_samples:
            ctx += "## Примеры стиля автора\n\n" + style_samples

        return self.llm.chat_with_skill(
            skill_prompt=self.skill,
            user_message=user_msg,
            system_extra=extra,
            context=ctx,
        )
