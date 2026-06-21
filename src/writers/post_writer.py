"""Post writer: two-step generation with fact extraction and validation."""

from __future__ import annotations

import json
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
    "приговор": "truecrime-post-writer",
    "маньяк": "truecrime-post-writer",
    "похищен": "truecrime-post-writer",
    "crime": "truecrime-post-writer",
    "murder": "truecrime-post-writer",
}

DEFAULT_SKILL = "post-writer-sms"

# Per-skill search query templates
CINEMA_QUERIES = [
    "{topic} новости сегодня",
    "new movies 2026 box office rating",
    "{topic} viral Reddit Threads",
    "лучшие фильмы 2026 рейтинг новинки",
    "{topic} скандал обсуждение",
]

TRUECRIME_QUERIES = [
    "{topic}",
    "раскрытое дело {topic}",
    "notorious crime solved conviction",
    "{topic} расследование приговор",
]

FACT_EXTRACTION_PROMPT = """\
Ты — фактчекер. Тебе даны результаты веб-поиска.

Задача: извлечь ТОЛЬКО конкретные проверенные факты. Никаких предположений, никаких додумываний.

Для каждого факта укажи:
- Что именно (название, цифра, имя, дата)
- Откуда (источник)

Если фактов недостаточно для поста — так и скажи.

Формат:
## Найденные факты
1. [факт] — источник: [url]
2. ...

## Вердикт
ДОСТАТОЧНО / МАЛО фактов

- ДОСТАТОЧНО — если есть хотя бы 2 конкретных проверенных факта (названия, цифры, имена, даты)
- МАЛО — если нет ни одного конкретного факта, только общие описания без имён/цифр

Если МАЛО — укажи чего именно не хватает."""

POST_FROM_FACTS_PROMPT = """\
Ты пишешь пост. У тебя есть извлечённые факты и стиль автора.

ЖЁСТКИЕ ПРАВИЛА:
1. Используй ТОЛЬКО факты из списка ниже. Ни одного факта, которого нет в списке.
2. Нет факта — не пиши. Лучше короткий пост из 2 проверенных фактов, чем длинный из 10 выдуманных.
3. Если фактов < 2 — напиши: "Не удалось найти достаточно свежих фактов по теме. Попробуйте уточнить запрос."
4. Конкретика: названия, цифры, имена. Никакой воды, никаких обобщений.
5. Пиши в стиле автора из примеров."""


def _detect_skill(topic: str) -> str:
    """Detect which skill to use based on topic keywords."""
    topic_lower = topic.lower()
    for keyword, skill_name in TOPIC_SKILLS.items():
        if keyword in topic_lower:
            return skill_name
    return DEFAULT_SKILL


def _get_search_queries(topic: str, skill_name: str) -> list[str]:
    """Generate search queries based on topic and skill."""
    templates = (
        CINEMA_QUERIES if "cinema" in skill_name
        else TRUECRIME_QUERIES if "truecrime" in skill_name
        else ["{topic}"]
    )
    return [q.format(topic=topic) for q in templates]


class PostWriter:
    """Two-step post writer: extract facts first, then write from facts only."""

    def __init__(self, llm: LLMClient, skills_dir: str = "./skills", config: Optional[dict] = None):
        self.llm = llm
        self.skills_dir = skills_dir
        self.config = config
        self.default_skill = load_skill(DEFAULT_SKILL, skills_dir)
        self._skill_cache = {DEFAULT_SKILL: self.default_skill}

    def _get_skill(self, skill_name: str) -> str:
        """Load and cache a skill by name."""
        if skill_name not in self._skill_cache:
            self._skill_cache[skill_name] = load_skill(skill_name, self.skills_dir)
        return self._skill_cache[skill_name]

    def _research_topic(self, topic: str, skill_name: str) -> str:
        """Run multiple search queries and return formatted results."""
        try:
            researcher = Researcher(self.llm, self.config)
            queries = _get_search_queries(topic, skill_name)

            all_results = []
            seen_titles = set()

            for q in queries:
                raw = researcher._fetch_raw(q)
                for r in raw:
                    title = r.get("title", "")
                    if title not in seen_titles:
                        seen_titles.add(title)
                        all_results.append(r)

            if not all_results:
                return ""

            parts = []
            for i, r in enumerate(all_results[:15], 1):
                title = r.get("title", "")
                desc = r.get("description", "")
                url = r.get("url", "")
                parts.append(f"{i}. {title}\n   {desc}\n   {url}")
            return "\n\n".join(parts)
        except Exception as e:
            return f"[Research error: {e}]"

    def _extract_facts(self, research_context: str, topic: str) -> tuple[str, bool]:
        """Step 1: Extract concrete facts from research results.

        Returns (facts_text, is_sufficient).
        """
        if not research_context or research_context.startswith("[Research"):
            return "Факты не найдены.", False

        messages = [
            {"role": "system", "content": FACT_EXTRACTION_PROMPT},
            {"role": "user", "content": f"Тема: {topic}\n\nРезультаты поиска:\n{research_context}"},
        ]
        response = self.llm.chat(messages, temperature=0.3, max_tokens=1500)

        lines = response.strip().splitlines()
        verdict_line = ""
        for line in lines:
            if "Вердикт" in line or "ДОСТАТОЧНО" in line or "МАЛО" in line:
                verdict_line = line
        is_sufficient = "ДОСТАТОЧНО" in verdict_line and "МАЛО" not in verdict_line
        return response, is_sufficient

    def _get_style_for_skill(self, all_styles: str, skill_name: str) -> str:
        """Extract relevant style examples for the given skill."""
        if not all_styles:
            return ""

        if "cinema" in skill_name:
            keywords = ["cinema", "кино"]
        elif "truecrime" in skill_name:
            keywords = ["true-crime", "тру-крайм", "truecrime"]
        else:
            return all_styles

        # Split by file separator and keep only relevant files
        blocks = all_styles.split("--- ")
        relevant = []
        for block in blocks:
            for kw in keywords:
                if kw.lower() in block[:100].lower():
                    relevant.append(block)
                    break

        return "--- ".join(relevant) if relevant else all_styles

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
        """Generate a post: research → extract facts → write from facts only.

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

        # 2. Research with targeted queries
        research_context = self._research_topic(topic, skill_name)

        # 3. Step 1: Extract facts
        facts, sufficient = self._extract_facts(research_context, topic)

        if not sufficient:
            return (
                f"Не удалось найти достаточно свежих фактов по теме «{topic}».\n\n"
                f"Вот что удалось найти:\n{facts}\n\n"
                f"Попробуйте уточнить запрос — например, указать конкретный фильм, актёра или событие."
            )

        # 4. Step 2: Write post from facts only
        is_specialized = "cinema" in skill_name or "truecrime" in skill_name

        # Load relevant style examples only
        style_ctx = self._get_style_for_skill(style_samples, skill_name)

        user_msg = f"""Тема: {topic}
Платформа: {platform}

## Проверенные факты (используй ТОЛЬКО их):
{facts}

## Примеры стиля автора (пиши в этом стиле!):
{style_ctx}

Напиши пост строго на основе этих фактов в стиле автора из примеров."""

        if is_specialized:
            # For specialized skills: skill = system, facts+style = user
            # No system_prompt override — skill already has all rules
            return self.llm.chat_with_skill(
                skill_prompt=skill,
                user_message=user_msg,
                system_extra=POST_FROM_FACTS_PROMPT,
                context="",
            )
        else:
            # Default skill: use full pipeline
            extra = (system_prompt or "") + "\n\n" + POST_FROM_FACTS_PROMPT
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
