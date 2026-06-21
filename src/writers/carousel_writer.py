"""Carousel writer + designer: creates carousel content and renders slides."""

from __future__ import annotations

import io
import json
import re
import urllib.parse
from pathlib import Path
from typing import Optional

import httpx
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from src.api.llm import LLMClient, load_skill, load_style_samples, load_context, load_system_prompt


class CarouselWriter:
    """Writes carousel slide content and optionally generates images."""

    def __init__(self, llm: LLMClient, skills_dir: str = "./skills", config: Optional[dict] = None):
        self.llm = llm
        self.skill = load_skill("carousel-writer-sms", skills_dir)
        self.config = config or {}

    def generate_movie_carousel(
        self,
        topic: str,
        style_samples: str = "",
        context: str = "",
        system_prompt: str = "",
    ) -> dict:
        """Generate a movie carousel: topics + caption + film slides.

        Returns:
            dict with:
              'topics' — list of 2-3 topic suggestions with reasons
              'selected_topic' — the best topic string
              'caption' — 3-4 sentence post caption
              'slides' — list of up to 5 film slides, each with:
                slide, type='poster', title, year, description
              'ordering' — description of sort order
        """
        # Check if this is a correction request
        is_correction = "ТЕКУЩАЯ ПОДБОРКА:" in topic or "ИСПРАВЛЕНИЯ ОТ ПОЛЬЗОВАТЕЛЯ:" in topic
        if is_correction:
            user_msg = f"""Пользователь просит внести исправления в текущую подборку.

{topic}

Внеси запрошенные исправления. Сохрани то, что пользователя устраивает. Замени только то, что нужно.
Ответь в том же JSON-формате что и раньше."""
        else:
            user_msg = f"""Задача: создай кино-карусель (подборку фильмов) по запросу: "{topic}"

Строго следуй шагам:

1. Предложи 2-3 конкретные темы подборок с обоснованием (тренды, рейтинги, охваты)
2. Выбери лучшую тему — напиши конкретную формулировку
3. Напиши подпись к посту (3-4 предложения, энергичный стиль, с интригой)
4. Подбери до 5 фильмов. Каждый фильм = 1 слайд. Укажи порядок сортировки.

⚠️ КРИТИЧЕСКИ ВАЖНО — НАЗВАНИЯ ФИЛЬМОВ:
- Поле "title_en" ОБЯЗАТЕЛЬНО — точное оригинальное название фильма на английском
- Поле "title" можно оставить пустым "" — русское название будет найдено автоматически через Кинопоиск
- НЕ придумывай русские названия самостоятельно — прокатчики называют фильмы совершенно иначе
- Примеры реальных прокатных названий: "The Fall Guy" → "Специально для коллег", "Knives Out" → "Достать ножи"
- Если знаешь точное русское прокатное название — укажи в "title", иначе оставь пустым

⚠️ КРИТИЧЕСКИ ВАЖНО — ФИЛЬМЫ ИЛИ СЕРИАЛЫ:
- Подборка должна содержать ЛИБО только фильмы, ЛИБО только сериалы
- Если тема про сериалы — подбирай только сериалы. Если про фильмы — только фильмы
- НЕ смешивай фильмы и сериалы в одной подборке
- Если тип не указан явно — по умолчанию подбирай фильмы
- Добавь поле "content_type": "films" или "series"

⚠️ КРИТИЧЕСКИ ВАЖНО — МИНИМАЛЬНЫЙ РЕЙТИНГ:
- Каждый фильм/сериал должен иметь рейтинг НЕ НИЖЕ 6.8 на Кинопоиске или IMDb
- НЕ включай фильмы с рейтингом ниже 6.8 — это порог качества
- Если не уверен в рейтинге — не включай фильм
- Лучше 3-4 отличных фильма, чем 5 посредственных
- Качество важнее количества

ВАЖНО: Ответь СТРОГО в формате JSON:
{{
  "topics": [
    {{"topic": "тема", "reason": "почему зайдёт"}},
    ...
  ],
  "selected_topic": "Лучшая тема — конкретная формулировка",
  "caption": "Текст подписи к посту (3-4 предложения)",
  "ordering": "по популярности / по хронологии / ...",
  "content_type": "films" или "series",
  "slides": [
    {{"slide": 1, "type": "poster", "title": "Русское прокатное название", "title_en": "Original Title", "year": 2024, "description": "2-3 предложения о чём фильм и чем примечателен"}},
    ...
  ]
}}

Правила:
- До 5 фильмов, не больше
- Описание каждого фильма: 2-3 предложения (режиссёр, фишка, награды)
- Без титульного слайда — только фильмы
- Порядок: от наиболее популярного к менее, либо по хронологии
- title = русское название с Кинопоиска, title_en = оригинальное"""

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

        result = self._parse_carousel_json(response)
        # Ensure required fields
        result.setdefault("topics", [])
        result.setdefault("selected_topic", topic)
        result.setdefault("caption", "")
        result.setdefault("ordering", "")
        result.setdefault("slides", [])
        return result

    def _parse_carousel_json(self, text: str) -> dict:
        """Extract carousel JSON from LLM response."""
        text = text.strip()

        # Strip markdown code blocks
        if text.startswith("```"):
            first_newline = text.index("\n") if "\n" in text else 3
            text = text[first_newline + 1:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        # Strip leading 'json' label after opening backticks
        if text.lower().startswith("json"):
            text = text[4:].strip()

        # Try direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try to find JSON object — use non-greedy match for inner braces,
        # then try to find balanced braces
        # Find the outermost { ... } by counting braces
        start = text.find("{")
        if start == -1:
            return {"raw": text, "slides": []}

        depth = 0
        best_end = -1
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    best_end = i + 1
                    break

        if best_end > start:
            candidate = text[start:best_end]
            try:
                return json.loads(candidate)
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
                lines = _wrap_text(header, font, 900, draw)
                for line in lines:
                    draw.text((90, y), line, fill=colors["text"], font=font)
                    y += 60
                y += 30

            # Body
            if body:
                lines = _wrap_text(body, font_regular, 900, draw)
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
            generated.append(filename)

        return generated

    # ------------------------------------------------------------------
    # Poster-based slide renderer (movie carousel)
    # ------------------------------------------------------------------

    @staticmethod
    def lookup_kinopoisk_title(title_en: str, year: Optional[int] = None) -> dict:
        """Look up a movie's Russian title via Brave search (finds Kinopoisk/Wikipedia results).

        Returns:
            dict with 'title_ru', 'title_en', 'year' or empty dict.
        """
        import os
        from dotenv import load_dotenv
        load_dotenv()
        brave_key = os.getenv("BRAVE_API_KEY")

        if not brave_key:
            return {}

        query = f'{title_en} {year} кинопоиск' if year else f'{title_en} кинопоиск'
        url = f"https://api.search.brave.com/res/v1/web/search?q={urllib.parse.quote_plus(query)}&count=5&search_lang=ru"

        try:
            with httpx.Client(timeout=5) as client:
                resp = client.get(url, headers={
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip",
                    "X-Subscription-Token": brave_key,
                })
                if resp.status_code != 200:
                    return {}

                data = resp.json()
                results = data.get("web", {}).get("results", [])

                for r in results:
                    title = r.get("title", "")
                    page_url = r.get("url", "")

                    # Extract Russian title from Kinopoisk or Wikipedia result
                    # Kinopoisk: "Улыбка 2 (2024) — трейлеры, видео — Кинопоиск"
                    # Wikipedia: "Улыбка 2 — Википедия"
                    ru_title = title

                    # Remove site markers and trailing descriptions
                    ru_title = re.sub(r'\s*[—–-]\s*.*$', '', ru_title)
                    # Remove year in parentheses
                    ru_title = re.sub(r'\s*\(\d{4}\)\s*', ' ', ru_title)
                    # Remove parenthetical descriptions like (фильм, 2024) or (Saw X)
                    ru_title = re.sub(r'\s*\([^)]*\)', '', ru_title)
                    # Remove trailing year like ", 2018"
                    ru_title = re.sub(r',\s*\d{4}\s*$', '', ru_title)
                    # Remove trailing descriptors
                    ru_title = re.sub(r'\s+(фильм|смотреть|трейлер|тизер|видео).*$', '', ru_title, flags=re.IGNORECASE)
                    ru_title = ru_title.strip()

                    # Only accept if it's a plausible Russian title (not just the English name)
                    if ru_title and "kinopoisk.ru" in page_url or "wikipedia.org" in page_url:
                        # Check it's not just the English title repeated
                        if ru_title.lower() != title_en.lower():
                            return {
                                "title_ru": ru_title,
                                "title_en": title_en,
                                "year": year,
                            }

        except Exception:
            pass

        return {}

    @staticmethod
    def resolve_russian_titles(slides: list[dict]) -> list[dict]:
        """Resolve Russian titles for all slides via Kinopoisk lookup.

        Only looks up titles that are missing or still in English.
        If title is already set and differs from title_en — keeps it as-is.
        Uses concurrent requests for speed.
        """
        import concurrent.futures

        def _resolve_one(slide):
            title_en = slide.get("title_en", "")
            if not title_en:
                return slide
            title = slide.get("title", "")
            year = slide.get("year")

            # If title is already set and it's NOT just the English name — keep it
            if title and title != title_en:
                return slide

            # Title is empty or same as English — look up on Kinopoisk
            try:
                kp = CarouselWriter.lookup_kinopoisk_title(title_en, year=year)
                if kp.get("title_ru"):
                    slide["title"] = kp["title_ru"]
                if not slide.get("title"):
                    slide["title"] = title_en
            except Exception:
                if not slide.get("title"):
                    slide["title"] = title_en
            return slide

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            slides = list(executor.map(_resolve_one, slides))

        return slides

    @staticmethod
    def search_movie_still(movie_title: str, year: Optional[int] = None, title_en: Optional[str] = None) -> Optional[bytes]:
        """Search for a movie still / film screenshot (NOT a poster).

        Args:
            movie_title: Russian title.
            year: Release year.
            title_en: Original English title (for better search results).
        """
        # Build search query — looking for film scenes, not posters
        if title_en:
            query = f"{title_en} {year if year else ''} movie still scene HD".strip()
        else:
            query = f"{movie_title} {year if year else ''} кадр из фильма".strip()
        query_encoded = urllib.parse.quote_plus(query)

        # Attempt 1: Bing image search (less aggressive bot detection)
        search_url = f"https://www.bing.com/images/search?q={query_encoded}&qft=+filterui:imagesize-large&form=HDRSC2"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        }

        try:
            with httpx.Client(timeout=15, follow_redirects=True, headers=headers) as client:
                resp = client.get(search_url)
                if resp.status_code == 200:
                    # Extract image URLs from the results page
                    page = resp.text
                    # Bing uses murl in media tags
                    img_urls = re.findall(r'murl&quot;:&quot;(https?://[^&]+)', page)
                    if not img_urls:
                        img_urls = re.findall(r'murl":"(https?://[^"]+)', page)
                    if not img_urls:
                        # Fallback: find any large image URL
                        img_urls = re.findall(r'https?://[^"\s<>]+?\.(?:jpg|jpeg|png|webp)', page, re.IGNORECASE)

                    # Try downloading the first few candidates
                    for url in img_urls[:5]:
                        url = url.replace("&amp;", "&")
                        try:
                            img_resp = client.get(url, timeout=10)
                            if img_resp.status_code == 200 and len(img_resp.content) > 30000:
                                # Verify it's a valid image
                                try:
                                    Image.open(io.BytesIO(img_resp.content)).verify()
                                    return img_resp.content
                                except Exception:
                                    continue
                        except Exception:
                            continue
        except Exception:
            pass

        return None

    @staticmethod
    def render_poster_slide(
        poster_bytes: bytes,
        title: str,
        year: Optional[int] = None,
        description: str = "",
        output_path: str = "./data/output",
        filename: str = "poster_slide.png",
    ) -> str:
        """Render a single movie poster slide.

        Layout (1080×1080 PNG):
          - Background: movie poster scaled to fill, centered crop
          - Bottom 40%: black gradient overlay (0% → 90% opacity)
          - Line 1: "Title (Year)" — bold sans-serif, large
          - Line 2: description — regular sans-serif, 30–40% smaller
          - Padding from edges, no text touching borders

        Args:
            poster_bytes: Raw image bytes of the poster.
            title: Movie title.
            year: Release year (optional).
            description: Short description / tagline.
            output_path: Directory to save the PNG.
            filename: Output filename.

        Returns:
            Path to the generated PNG.
        """
        out_dir = Path(output_path)
        out_dir.mkdir(parents=True, exist_ok=True)

        # --- Load & resize poster to 1080×1080 (cover fit) ---
        poster_img = Image.open(io.BytesIO(poster_bytes)).convert("RGBA")
        poster_img = _cover_crop(poster_img, 1080, 1080)

        canvas_w, canvas_h = 1080, 1080

        # --- Blur bottom 1/3 with soft fade-out toward the edge ---
        blur_edge = int(canvas_h * 0.67)  # where blur fades to zero (top of bottom 1/3)
        blur_fade_zone = int(canvas_h * 0.12)  # transition band above blur_edge
        blur_start = blur_edge - blur_fade_zone  # ~55% height — blur begins here at full strength

        # Full blur of the entire bottom region (blur_start → bottom)
        bottom_crop = poster_img.crop((0, blur_start, canvas_w, canvas_h))
        blurred_crop = bottom_crop.filter(ImageFilter.GaussianBlur(radius=22))

        # Build alpha mask for smooth fade: 0 at blur_start (full original),
        # 1 at blur_edge (full blur), stays 1 below blur_edge
        import numpy as np
        fade_height = blur_edge - blur_start
        below_height = canvas_h - blur_edge

        fade_mask = np.linspace(0, 1, fade_height, dtype=np.float32).reshape(-1, 1)  # smooth 0→1
        below_mask = np.ones((below_height, 1), dtype=np.float32)
        full_mask = np.concatenate([fade_mask, below_mask], axis=0)  # (h, 1)
        full_mask = np.tile(full_mask, (1, canvas_w))[:, :, np.newaxis]  # (h, w, 1)

        # Convert to numpy for blending
        orig_arr = np.array(bottom_crop, dtype=np.float32)  # original pixels
        blur_arr = np.array(blurred_crop, dtype=np.float32)  # blurred pixels

        # Blend: result = original * (1-mask) + blurred * mask
        blended = (orig_arr * (1 - full_mask) + blur_arr * full_mask).astype(np.uint8)
        poster_img.paste(Image.fromarray(blended, 'RGBA'), (0, blur_start))

        # --- Build gradient overlay: bottom ~40% with strong darkening ---
        # Bottom 1/3 gets heavy overlay, with soft transition above
        gradient = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))

        # Transition zone: 60%→blur_edge height — light dimming (alpha 0→100)
        trans_top = int(canvas_h * 0.60)
        trans_height = blur_edge - trans_top
        for y in range(trans_height):
            progress = y / trans_height
            alpha = int(100 * progress)
            row = Image.new("RGBA", (canvas_w, 1), (0, 0, 0, alpha))
            gradient.paste(row, (0, trans_top + y))

        # Main dark zone: blur_edge→100% — heavy dimming (alpha 100→230)
        dark_height = canvas_h - blur_edge
        for y in range(dark_height):
            progress = y / dark_height
            alpha = int(100 + 130 * progress)
            row = Image.new("RGBA", (canvas_w, 1), (0, 0, 0, alpha))
            gradient.paste(row, (0, blur_edge + y))

        # --- Composite: poster + gradient ---
        canvas = Image.alpha_composite(poster_img, gradient)

        # --- Draw text ---
        draw = ImageDraw.Draw(canvas)

        # Fonts
        font_bold, font_regular, font_small = _load_fonts()

        # Title line
        title_text = f"{title} ({year})" if year else title
        title_size = 52  # will use font_bold which is 48–56 range
        # Reload font_bold at desired size
        font_title = _load_font_at_size(bold=True, size=title_size)
        font_desc = _load_font_at_size(bold=False, size=int(title_size * 0.6))  # ~40% smaller

        # --- Text positioning ---
        padding_x = 60
        padding_bottom = 70
        line_gap = 20

        max_text_width = canvas_w - padding_x * 2

        # Wrap title
        title_lines = _wrap_text(title_text, font_title, max_text_width, draw)
        # Wrap description
        desc_lines = _wrap_text(description, font_desc, max_text_width, draw) if description else []

        total_text_height = (
            len(title_lines) * (title_size + 8)
            + line_gap
            + len(desc_lines) * (int(title_size * 0.6) + 6)
        )

        # Start y so text bottom aligns with padding_bottom
        y = canvas_h - padding_bottom - total_text_height

        # Draw title
        text_color = (255, 255, 255, 240)
        for line in title_lines:
            draw.text((padding_x, y), line, fill=text_color, font=font_title)
            y += title_size + 8

        y += line_gap

        # Draw description
        desc_color = (230, 230, 230, 220)
        for line in desc_lines:
            draw.text((padding_x, y), line, fill=desc_color, font=font_desc)
            y += int(title_size * 0.6) + 6

        # --- Save ---
        canvas = canvas.convert("RGB")
        filepath = out_dir / filename
        canvas.save(filepath, "PNG", quality=95)
        return str(filepath)



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


def _cover_crop(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    """Resize and center-crop image to fill target dimensions."""
    src_w, src_h = img.size
    scale = max(target_w / src_w, target_h / src_h)
    new_w = int(src_w * scale)
    new_h = int(src_h * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    return img.crop((left, top, left + target_w, top + target_h))


def _load_fonts() -> tuple:
    """Load bold, regular, small fonts (fallback to default)."""
    bold_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]
    regular_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    font_bold = _pick_font(bold_paths, 48)
    font_regular = _pick_font(regular_paths, 36)
    font_small = _pick_font(regular_paths, 28)
    return font_bold, font_regular, font_small


def _load_font_at_size(bold: bool = True, size: int = 48) -> ImageFont.FreeTypeFont:
    """Load a font at a specific size."""
    if bold:
        paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        ]
    else:
        paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        ]
    return _pick_font(paths, size)


def _pick_font(paths: list[str], size: int) -> ImageFont.FreeTypeFont:
    """Pick first available font from paths, fallback to default."""
    for p in paths:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()
