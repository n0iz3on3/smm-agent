"""Carousel writer + designer: creates carousel content and renders slides."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from src.api.llm import LLMClient, load_skill, load_style_samples, load_context, load_system_prompt


class CarouselWriter:
    """Writes carousel slide content and optionally generates images."""

    def __init__(self, llm: LLMClient, skills_dir: str = "./skills", config: Optional[dict] = None):
        self.llm = llm
        self.skill = load_skill("carousel-writer-sms", skills_dir)
        self.config = config or {}

    def write_carousel(
        self,
        topic: str,
        platform: str = "instagram",
        slide_count: int = 10,
        format_type: str = "listicle",
        style_samples: str = "",
        context: str = "",
        system_prompt: str = "",
    ) -> dict:
        """Generate carousel slide content.

        Returns:
            dict with 'slides' list, each having 'header', 'body', 'slide_number'
        """
        user_msg = f"""Создай карусель на тему: {topic}

Платформа: {platform}
Количество слайдов: {slide_count}
Формат: {format_type} (listicle | framework | before_after | data_story | case_study)

ВАЖНО: Ответь в формате JSON:
{{
  "title": "Название карусели",
  "slides": [
    {{"slide": 1, "type": "cover", "header": "...", "body": "..."}},
    {{"slide": 2, "type": "context", "header": "...", "body": "..."}},
    {{"slide": 3, "type": "body", "header": "...", "body": "..."}},
    ...
    {{"slide": N, "type": "cta", "header": "...", "body": "..."}}
  ]
}}"""

        extra = system_prompt or ""
        ctx = ""
        if context:
            ctx += context + "\n\n"
        if style_samples:
            ctx += "## Примеры стиля автора\n\n" + style_samples

        response = self.llm.chat_with_skill(
            skill_prompt=self.skill,
            user_message=user_msg,
            system_extra=extra,
            context=ctx,
        )

        # Parse JSON from response
        return self._parse_carousel_json(response)

    def _parse_carousel_json(self, text: str) -> dict:
        """Extract carousel JSON from LLM response."""
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0]
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to find JSON object in text
            match = re.search(r'\{[\s\S]*\}', text)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
            return {"raw": text, "slides": []}

    def render_carousel_images(
        self,
        carousel_data: dict,
        output_dir: str = "./data/output",
        design_style: str = "dark_modern",
    ) -> list[str]:
        """Generate carousel slide images using Pillow or an image generation API.

        Args:
            carousel_data: Parsed carousel from write_carousel()
            output_dir: Where to save images
            design_style: Visual style preset

        Returns:
            List of generated image paths
        """
        try:
            from PIL import Image, ImageDraw, ImageFont
        except ImportError:
            raise ImportError("Pillow required for carousel rendering: pip install Pillow")

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        slides = carousel_data.get("slides", [])
        if not slides:
            return []

        # Design presets
        styles = {
            "dark_modern": {"bg": (18, 18, 24), "text": (255, 255, 255), "accent": (99, 102, 241)},
            "light_clean": {"bg": (255, 255, 255), "text": (30, 30, 30), "accent": (59, 130, 246)},
            "warm_gradient": {"bg": (255, 107, 53), "text": (255, 255, 255), "accent": (255, 255, 255)},
            "dark_red": {"bg": (20, 10, 10), "text": (255, 255, 255), "accent": (220, 38, 38)},
        }

        colors = styles.get(design_style, styles["dark_modern"])
        generated = []

        # Try to find a good font
        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
        ]
        font_regular_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/TTF/DejaVuSans.ttf",
        ]

        font = None
        font_regular = None
        font_small = None
        for fp in font_paths:
            if Path(fp).exists():
                font = ImageFont.truetype(fp, 48)
                font_small = ImageFont.truetype(fp, 32)
                break
        for fp in font_regular_paths:
            if Path(fp).exists():
                font_regular = ImageFont.truetype(fp, 36)
                break

        if font is None:
            font = ImageFont.load_default()
            font_regular = font
            font_small = font

        for slide in slides:
            num = slide.get("slide", 0)
            slide_type = slide.get("type", "body")
            header = slide.get("header", "")
            body = slide.get("body", "")

            # Instagram square 1080x1080
            img = Image.new("RGB", (1080, 1080), colors["bg"])
            draw = ImageDraw.Draw(img)

            # Accent bar at top
            bar_height = 8
            draw.rectangle([0, 0, 1080, bar_height], fill=colors["accent"])

            # Slide number badge
            draw.rounded_rectangle(
                [60, 60, 160, 110],
                radius=8,
                fill=colors["accent"],
            )
            draw.text((75, 63), f"{num}/{len(slides)}", fill=(255, 255, 255), font=font_small)

            y = 160

            # Header
            if header:
                # Word wrap header
                lines = self._wrap_text(header, font, 900, draw)
                for line in lines:
                    draw.text((90, y), line, fill=colors["text"], font=font)
                    y += 60
                y += 30

            # Body
            if body:
                lines = self._wrap_text(body, font_regular, 900, draw)
                for line in lines:
                    draw.text((90, y), line, fill=(*colors["text"][:3],), font=font_regular)
                    y += 48

            # Cover slide special treatment
            if slide_type == "cover":
                # Center everything
                pass  # Already drawn from top, which looks good for covers

            filename = f"slide_{num:02d}.png"
            filepath = output_path / filename
            img.save(filepath, "PNG")
            generated.append(str(filepath))

        return generated

    @staticmethod
    def _wrap_text(text: str, font, max_width: int, draw) -> list[str]:
        """Word-wrap text to fit within max_width pixels."""
        words = text.split()
        lines = []
        current = ""
        for word in words:
            test = f"{current} {word}".strip()
            bbox = draw.textbbox((0, 0), test, font=font)
            if bbox[2] - bbox[0] <= max_width:
                current = test
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines
