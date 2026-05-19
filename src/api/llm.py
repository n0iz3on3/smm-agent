"""LLM API abstraction layer."""

import os
from pathlib import Path
from typing import Optional

import httpx
import yaml
from dotenv import load_dotenv

# Load .env from project root
load_dotenv(Path(__file__).parent.parent.parent / ".env")


def load_config(config_path: str = "config.yaml") -> dict:
    """Load config from YAML, expanding env vars."""
    p = Path(config_path)
    if not p.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")
    with open(p) as f:
        raw = f.read()
    # Expand ${ENV_VAR} patterns
    import re
    def _env_replace(match):
        return os.environ.get(match.group(1), match.group(0))
    expanded = re.sub(r'\$\{(\w+)\}', _env_replace, raw)
    return yaml.safe_load(expanded)


class LLMClient:
    """Thin wrapper around OpenAI-compatible chat completions API."""

    def __init__(self, config: Optional[dict] = None, config_path: str = "config.yaml"):
        if config is None:
            config = load_config(config_path)
        llm_cfg = config["llm"]
        self.api_key = llm_cfg["api_key"]
        self.model = llm_cfg["model"]
        self.base_url = llm_cfg.get("base_url", "https://api.openai.com/v1").rstrip("/")
        self.temperature = config.get("generation", {}).get("temperature", 0.8)
        self.max_tokens = config.get("generation", {}).get("max_tokens", 2000)
        self.client = httpx.Client(timeout=120)

    def chat(
        self,
        messages: list[dict],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        model: Optional[str] = None,
    ) -> str:
        """Send a chat completion request and return the assistant message."""
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model or self.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.temperature,
            "max_completion_tokens": max_tokens or self.max_tokens,
        }
        resp = self.client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    def chat_with_skill(
        self,
        skill_prompt: str,
        user_message: str,
        system_extra: str = "",
        context: str = "",
    ) -> str:
        """Chat using a skill as the system prompt."""
        parts = [skill_prompt]
        if system_extra:
            parts.append(f"\n\n## Additional Instructions\n\n{system_extra}")
        if context:
            parts.append(f"\n\n## User Context / Style\n\n{context}")
        messages = [
            {"role": "system", "content": "\n".join(parts)},
            {"role": "user", "content": user_message},
        ]
        return self.chat(messages)


def load_skill(skill_name: str, skills_dir: str = "./skills") -> str:
    """Load a SKILL.md from the skills directory."""
    skill_path = Path(skills_dir) / skill_name / "SKILL.md"
    if not skill_path.exists():
        raise FileNotFoundError(f"Skill not found: {skill_path}")
    return skill_path.read_text(encoding="utf-8")


def load_style_samples(samples_dir: str = "./data/style_samples") -> str:
    """Load all style sample files and combine them."""
    p = Path(samples_dir)
    if not p.exists() or not any(p.iterdir()):
        return ""
    parts = []
    for f in sorted(p.iterdir()):
        if f.is_file() and f.suffix in (".txt", ".md"):
            parts.append(f"--- {f.name} ---\n{f.read_text(encoding='utf-8')}")
    return "\n\n".join(parts)


def load_context(context_file: str = "./data/social-media-context.md") -> str:
    """Load the social media context file."""
    p = Path(context_file)
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8")


def load_system_prompt(prompt_file: str = "./data/system_prompt.md") -> str:
    """Load custom system prompt override."""
    p = Path(prompt_file)
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8")
