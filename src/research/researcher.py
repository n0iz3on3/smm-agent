"""Researcher: поиск виральных тем через web search + LLM фильтрация."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from src.api.llm import LLMClient, load_config


RESEARCH_SYSTEM = """\
Ты — эксперт по виральному контенту для соцсетей.
Твои платформы: Telegram, Instagram, Threads.
Твоя аудитория — русскоязычная.

Тебе предоставят список найденных тем/статей.
Твоя задача:
1. Отфильтровать темы с высоким виральным потенциалом
2. Для каждой темы дать: заголовок, почему зайдёт, какой формат лучше (пост/карусель/тред), пример хука
3. Отсортировать по виральности (лучшие первыми)

Ответ в формате JSON:
{
  "topics": [
    {
      "title": "...",
      "viral_reason": "...",
      "best_format": "post|carousel|thread",
      "hook_example": "...",
      "source": "..."
    }
  ]
}
"""


class Researcher:
    """Finds viral topics via web search, filters with LLM."""

    def __init__(self, llm: LLMClient, config: Optional[dict] = None):
        self.llm = llm
        self.config = config or load_config()
        self.topic = self.config.get("topic", "")
        self.research_cfg = self.config.get("research", {})

    def search_viral_topics(self, topic: Optional[str] = None) -> list[dict]:
        """Search for viral topics related to the given theme.

        Uses httpx to call a search API. Override _fetch_raw for different providers.
        """
        import httpx

        query = topic or self.topic
        if not query:
            raise ValueError("No topic specified. Set 'topic' in config or pass as argument.")

        raw_results = self._fetch_raw(query)
        if not raw_results:
            return []

        # Filter and rank with LLM
        prompt = f"Тема для поиска: {query}\n\nНайденные статьи/темы:\n{json.dumps(raw_results, ensure_ascii=False, indent=2)}"
        response = self.llm.chat(
            messages=[
                {"role": "system", "content": RESEARCH_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            max_tokens=3000,
        )

        try:
            # Try to extract JSON from response
            text = response.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0]
            parsed = json.loads(text)
            return parsed.get("topics", [])
        except json.JSONDecodeError:
            return [{"raw_response": response}]

    def _fetch_raw(self, query: str) -> list[dict]:
        """Fetch raw search results. Uses Brave Search API by default.

        Set BRAVE_API_KEY env var for Brave Search.
        Override this method for other search providers.
        """
        import httpx
        import os

        # Try config first, then env var
        brave_key = self.config.get("brave", {}).get("api_key") or os.environ.get("BRAVE_API_KEY")
        if not brave_key:
            # Fallback: return a placeholder so the LLM can still work
            return [{"title": f"No search API configured for: {query}", "note": "Set BRAVE_API_KEY or override _fetch_raw"}]

        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": brave_key,
        }
        lang = self.research_cfg.get("language", "ru")
        region = self.research_cfg.get("region", "ru")

        results = []
        for q in [query, f"{query} viral 2025", f"{query} тренд"]:
            resp = httpx.get(
                "https://api.search.brave.com/res/v1/web/search",
                params={"q": q, "count": 5, "search_lang": lang, "country": region},
                headers=headers,
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("web", {}).get("results", []):
                    results.append({
                        "title": item.get("title", ""),
                        "description": item.get("description", ""),
                        "url": item.get("url", ""),
                    })

        # Deduplicate by title
        seen = set()
        unique = []
        for r in results:
            if r["title"] not in seen:
                seen.add(r["title"])
                unique.append(r)
        return unique
