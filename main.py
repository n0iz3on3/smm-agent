#!/usr/bin/env python3
"""SMM Agent CLI — генерация СММ-контента с помощью AI."""

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime

import yaml

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from src.api.llm import LLMClient, load_config, load_skill, load_style_samples, load_context, load_system_prompt
from src.research.researcher import Researcher
from src.writers.post_writer import PostWriter
from src.writers.hook_writer import HookWriter
from src.writers.carousel_writer import CarouselWriter
from src.writers.content_repurposer import ContentRepurposer


def save_output(content: str, prefix: str, output_dir: str = "./data/output"):
    """Save content to a timestamped file."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{prefix}_{ts}.md"
    filepath = out / filename
    filepath.write_text(content, encoding="utf-8")
    print(f"💾 Сохранено: {filepath}")
    return str(filepath)


def cmd_research(args, config: dict):
    """Search for viral topics."""
    llm = LLMClient(config)
    researcher = Researcher(llm, config)
    topics = researcher.search_viral_topics(topic=args.topic)
    if topics:
        print("\n🔥 Виральные темы:\n")
        for i, t in enumerate(topics, 1):
            print(f"{i}. {t.get('title', '—')}")
            print(f"   Почему зайдёт: {t.get('viral_reason', '—')}")
            print(f"   Формат: {t.get('best_format', '—')}")
            print(f"   Хук: {t.get('hook_example', '—')}")
            print(f"   Источник: {t.get('source', '—')}")
            print()
        if args.save:
            save_output(json.dumps(topics, ensure_ascii=False, indent=2), "research")
    else:
        print("Ничего не найдено.")


def cmd_post(args, config: dict):
    """Generate a post."""
    llm = LLMClient(config)
    writer = PostWriter(llm, config["paths"]["skills_dir"], config)
    style = load_style_samples(config["paths"]["style_samples"])
    context = load_context(config["paths"]["context_file"])
    sys_prompt = load_system_prompt(config["paths"]["system_prompt"])

    result = writer.write_post(
        topic=args.topic,
        platform=args.platform,
        content_type=args.type,
        angle=args.angle or "",
        style_samples=style,
        context=context,
        system_prompt=sys_prompt,
    )
    print(f"\n📝 Пост ({args.platform}):\n")
    print(result)
    if args.save:
        save_output(result, f"post_{args.platform}")


def cmd_hooks(args, config: dict):
    """Generate hooks."""
    llm = LLMClient(config)
    writer = HookWriter(llm, config["paths"]["skills_dir"], config)
    style = load_style_samples(config["paths"]["style_samples"])
    context = load_context(config["paths"]["context_file"])

    result = writer.write_hooks(
        topic=args.topic,
        platform=args.platform,
        count=args.count,
        patterns=args.patterns.split(",") if args.patterns else None,
        style_samples=style,
        context=context,
    )
    print(f"\n🪝 Хуки ({args.platform}):\n")
    print(result)
    if args.save:
        save_output(result, "hooks")


def cmd_carousel(args, config: dict):
    """Generate carousel."""
    llm = LLMClient(config)
    writer = CarouselWriter(llm, config["paths"]["skills_dir"], config)
    style = load_style_samples(config["paths"]["style_samples"])
    context = load_context(config["paths"]["context_file"])
    sys_prompt = load_system_prompt(config["paths"]["system_prompt"])

    carousel = writer.write_carousel(
        topic=args.topic,
        platform=args.platform,
        slide_count=args.slides,
        format_type=args.format,
        style_samples=style,
        context=context,
        system_prompt=sys_prompt,
    )

    print(f"\n🎠 Карусель ({args.platform}):\n")
    if carousel.get("slides"):
        print(f"Название: {carousel.get('title', '—')}\n")
        for s in carousel["slides"]:
            print(f"  Слайд {s.get('slide', '?')} [{s.get('type', '?')}]:")
            print(f"    Заголовок: {s.get('header', '—')}")
            print(f"    Текст: {s.get('body', '—')}")
            print()
    else:
        print(carousel.get("raw", "Ошибка генерации"))

    # Generate images if requested
    if args.design:
        print("🎨 Генерация изображений карусели...")
        images = writer.render_carousel_images(
            carousel,
            output_dir=config["paths"]["output"],
            design_style=args.design,
        )
        if images:
            print(f"✅ Сгенерировано {len(images)} слайдов:")
            for img in images:
                print(f"   {img}")
        else:
            print("❌ Не удалось сгенерировать изображения")

    if args.save:
        save_output(json.dumps(carousel, ensure_ascii=False, indent=2), "carousel")


def cmd_repurpose(args, config: dict):
    """Repurpose content."""
    llm = LLMClient(config)
    repurposer = ContentRepurposer(llm, config["paths"]["skills_dir"], config)
    style = load_style_samples(config["paths"]["style_samples"])
    context = load_context(config["paths"]["context_file"])

    source = args.content
    if args.file:
        source = Path(args.file).read_text(encoding="utf-8")

    result = repurposer.repurpose(
        source_content=source,
        target_platforms=args.platforms.split(",") if args.platforms else None,
        target_formats=args.formats.split(",") if args.formats else None,
        style_samples=style,
        context=context,
    )
    print(f"\n♻️ Переработанный контент:\n")
    print(result)
    if args.save:
        save_output(result, "repurposed")


def cmd_context(args, config: dict):
    """Setup social media context (voice, tone, pillars)."""
    ctx_file = Path(config["paths"]["context_file"])
    if args.show:
        if ctx_file.exists():
            print(ctx_file.read_text(encoding="utf-8"))
        else:
            print("Контекст ещё не создан. Создай его в data/social-media-context.md")
        return

    if args.edit:
        editor = __import__("os").environ.get("EDITOR", "nano")
        __import__("os").system(f"{editor} {ctx_file}")
        return

    print("📝 Контекст хранится в: data/social-media-context.md")
    print("Создай/отредактируй этот файл с описанием твоего голоса, тона, и контент-пилларов.")


def main():
    parser = argparse.ArgumentParser(
        prog="smm-agent",
        description="SMM Agent — генерация СММ-контента с AI",
    )
    parser.add_argument("-c", "--config", default="config.yaml", help="Path to config file")

    sub = parser.add_subparsers(dest="command", help="Available commands")

    # research
    p_research = sub.add_parser("research", help="Find viral topics")
    p_research.add_argument("topic", nargs="?", help="Topic to search (overrides config)")
    p_research.add_argument("--save", action="store_true", help="Save results to file")

    # post
    p_post = sub.add_parser("post", help="Generate a post")
    p_post.add_argument("topic", help="Post topic")
    p_post.add_argument("-p", "--platform", default="telegram", choices=["telegram", "instagram", "threads"])
    p_post.add_argument("-t", "--type", default="storytelling", choices=["storytelling", "educational", "engagement", "promotional"])
    p_post.add_argument("-a", "--angle", default="", help="Specific angle or CTA")
    p_post.add_argument("--save", action="store_true")

    # hooks
    p_hooks = sub.add_parser("hooks", help="Generate hooks")
    p_hooks.add_argument("topic", help="Hook topic")
    p_hooks.add_argument("-p", "--platform", default="telegram", choices=["telegram", "instagram", "threads"])
    p_hooks.add_argument("-n", "--count", type=int, default=5, help="Number of variants")
    p_hooks.add_argument("--patterns", default="", help="Comma-separated patterns")
    p_hooks.add_argument("--save", action="store_true")

    # carousel
    p_carousel = sub.add_parser("carousel", help="Generate carousel")
    p_carousel.add_argument("topic", help="Carousel topic")
    p_carousel.add_argument("-p", "--platform", default="instagram", choices=["telegram", "instagram", "threads"])
    p_carousel.add_argument("-s", "--slides", type=int, default=10, help="Number of slides")
    p_carousel.add_argument("-f", "--format", default="listicle",
                            choices=["listicle", "framework", "before_after", "data_story", "case_study"])
    p_carousel.add_argument("--design", default="", help="Generate images with style: dark_modern, light_clean, warm_gradient, dark_red")
    p_carousel.add_argument("--save", action="store_true")

    # repurpose
    p_repurpose = sub.add_parser("repurpose", help="Repurpose content")
    p_repurpose.add_argument("content", nargs="?", default="", help="Source content text")
    p_repurpose.add_argument("--file", "-f", help="Read source from file")
    p_repurpose.add_argument("--platforms", default="", help="Comma-separated target platforms")
    p_repurpose.add_argument("--formats", default="", help="Comma-separated target formats")
    p_repurpose.add_argument("--save", action="store_true")

    # context
    p_context = sub.add_parser("context", help="Manage social media context")
    p_context.add_argument("--show", action="store_true", help="Show current context")
    p_context.add_argument("--edit", action="store_true", help="Open context in editor")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    try:
        config = load_config(args.config)
    except FileNotFoundError:
        print(f"❌ Конфиг не найден: {args.config}")
        print("Скопируй config.yaml.example и заполни.")
        sys.exit(1)

    commands = {
        "research": cmd_research,
        "post": cmd_post,
        "hooks": cmd_hooks,
        "carousel": cmd_carousel,
        "repurpose": cmd_repurpose,
        "context": cmd_context,
    }

    cmd_fn = commands.get(args.command)
    if cmd_fn:
        cmd_fn(args, config)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
