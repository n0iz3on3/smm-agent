"""Post writer: generates social media posts with topic-based skill routing and research."""

from __future__ import annotations

from typing import Optional

from src.api.llm import LLMClient, load_skill, load_style_samples, load_context, load_system_prompt
from src.research.researcher import Researcher


# Topic → skill mapping
TOPIC_SKILLS = {
    "cinema": "cinema-post-writer",
    "кино": "cinema-post-writer",
    "фильм": "cinema-post-writer",
    "сериал": "cinema-post-writer",
    "премьера": "cinema-post-writer",
    "актер": "cinema-post-writer",
    "актёр": "cinema-post-writer",
    "режиссер": "cinema-post-writer",
    "режиссёр": "cinema-post-writer",
    "rotten": "cinema-post-writer",
    "imdb": "cinema-post-writer",
    "кинопоиск": "cinema-post-writer",
    "movie": "cinema-post-writer",
    "truecrime": "truecrime-post-writer",
    "тру-крайм": "truecrime-post-writer",
    "трукрайм": "truecrime-post-writer",
    "преступлен": "truecrime-post-writer",
    "убийств": "truecrime-post-writer",
    "расследован": "truecrime-post-writer",
    "серийн": "truecrime-post-writer",
    "суд": "truecrime-post-writer",
    "приговор": "truecrime-post-writer",
    "дело": "truecrime-post-writer",
    "маньяк": "truecrime-post-writer",
    "похищен": "truecrime-post-writer",
    "crime": "truecrime-post-writer",
    "murder": "truecrime-post-writer",
}

DEFAULT_SKILL = "post-writer-sms"


def _detect_skill(topic: str) -> str:
    """Detect which skill to use based on topic keywords."""
    topic_lower = topic.lower()
    for keyword, skill_name in TOPIC_SKILLS.items():
        if keyword in topic_lower:
            return skill_name
    return DEFAULT_SKILL


class PostWriter:
    """Writes posts with topic-based skill routing and research."""

    def __init__(self, llm: LLMClient, skills_dir: str = "./skills", config: Optional[dict] = None):
        self.llm = llm
        self.skills_dir = skills_dir
        self.config = config
        # Pre-load default skill
        self.default_skill = load_skill(DEFAULT_SKILL, skills_dir)
        self._skill_cache = {DEFAULT_SKILL: self.default_skill}

    def _get_skill(self, skill_name: str) -> str:
        """Load and cache a skill by name."""
        if skill_name not in self._skill_cache:
            self._skill_cache[skill_name] = load_skill(skill_name, self.skills_dir)
        return self._skill_cache[skill_name]

    def _research_topic(self, topic: str) -> str:
        """Run web search and return formatted results for context."""
        try:
            researcher = Researcher(self.llm, self.config)
            raw_results = researcher._fetch_raw(topic)
            if not raw_results:
                return ""
            parts = []
            for i, r in enumerate(raw_results[:10], 1):
                title = r.get("title", "")
                desc = r.get("description", "")
                url = r.get("url", "")
                parts.append(f"{i}. {title}\n   {desc}\n   {url}")
            return "\n\n".join(parts)
        except Exception as e:
            return f"[Research error: {e}]"

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
        """Generate a social media post with auto-detected skill and research.

        Args:
            topic: What to write about
            platform: telegram | instagram | threads
            content_type: storytelling | educational | engagement | promotional
            angle: Specific angle or CTA
            style_samples: User's style examples
            context: Social media context (voice, tone, pillars)
            system_prompt: Custom system prompt override
        """
        # 1. Detect skill
        skill_name = _detect_skill(topic)
        skill = self._get_skill(skill_name)

        # 2. Research
        research_context = self._research_topic(topic)

        # 3. Build messages
        user_msg = f"""Напиши пост на тему: {topic}

Платформа: {platform}
Тип контента: {content_type}
{f'Угол/CTA: {angle}' if angle else ''}

## Результаты поиска (используй эти факты!)
{research_context}

Сгенерируй готовый пост на основе найденных фактов. Если фактов недостаточно — напиши что не удалось найти информацию."""

        extra = system_prompt or ""
        ctx = ""
        if context:
            ctx += context + "\n\n"
        if style_samples:
            ctx += "## Примеры стиля автора\n\n" + style_samples

        return self.llm.chat_with_skill(
            skill_prompt=skill,
            user_message=user_msg,
            system_extra=extra,
            context=ctx,
        )
