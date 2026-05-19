"""FastAPI web application for SMM Agent."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Add project root
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.api.llm import (
    LLMClient, load_config, load_skill, load_style_samples,
    load_context, load_system_prompt,
)
from src.research.researcher import Researcher
from src.writers.post_writer import PostWriter
from src.writers.hook_writer import HookWriter
from src.writers.carousel_writer import CarouselWriter
from src.writers.content_repurposer import ContentRepurposer

# Init
config = load_config(str(PROJECT_ROOT / "config.yaml"))
llm = LLMClient(config, config_path=str(PROJECT_ROOT / "config.yaml"))

app = FastAPI(title="SMM Agent", version="0.1.0")
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")
_templates_dir = str(Path(__file__).parent / "templates")
templates = Jinja2Templates(directory=_templates_dir)

MODEL_NAME = config.get("llm", {}).get("model", "")
GENERATIONS_LOG = Path(config.get("paths", {}).get("generations_log", "./data/generations.jsonl"))


def _save_generation(entry: dict):
    """Append a generation record to JSONL log."""
    GENERATIONS_LOG.parent.mkdir(parents=True, exist_ok=True)
    entry["id"] = _next_id()
    entry["created_at"] = datetime.now(timezone.utc).isoformat()
    with open(GENERATIONS_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry["id"]


def _load_generations() -> list[dict]:
    """Load all generations from JSONL log."""
    if not GENERATIONS_LOG.exists():
        return []
    entries = []
    with open(GENERATIONS_LOG, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return entries


def _next_id() -> int:
    """Get next sequential ID."""
    entries = _load_generations()
    if not entries:
        return 1
    return max(e.get("id", 0) for e in entries) + 1


def _render(request, template: str, **kwargs):
    """Render template with base context (Starlette 1.0 signature)."""
    return templates.TemplateResponse(
        request, template, {"model": MODEL_NAME, **kwargs},
    )


def _get_helpers():
    """Load style/context/system_prompt."""
    return {
        "style": load_style_samples(config["paths"]["style_samples"]),
        "context": load_context(config["paths"]["context_file"]),
        "system_prompt": load_system_prompt(config["paths"]["system_prompt"]),
    }


# --- Pages ---

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return _render(request, "index.html", topic=config.get("topic", ""))


@app.get("/post", response_class=HTMLResponse)
async def post_page(request: Request):
    return _render(request, "post.html")


@app.get("/hooks", response_class=HTMLResponse)
async def hooks_page(request: Request):
    return _render(request, "hooks.html")


@app.get("/carousel", response_class=HTMLResponse)
async def carousel_page(request: Request):
    return _render(request, "carousel.html")


@app.get("/research", response_class=HTMLResponse)
async def research_page(request: Request):
    return _render(request, "research.html")


@app.get("/repurpose", response_class=HTMLResponse)
async def repurpose_page(request: Request):
    return _render(request, "repurpose.html")


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    ctx = load_context(config["paths"]["context_file"])
    sysp = load_system_prompt(config["paths"]["system_prompt"])
    return _render(request, "settings.html", context=ctx, system_prompt=sysp)


# --- API endpoints ---

@app.post("/api/post")
async def api_post(
    topic: str = Form(...),
    platform: str = Form("telegram"),
    content_type: str = Form("storytelling"),
    angle: str = Form(""),
):
    h = _get_helpers()
    writer = PostWriter(llm, config["paths"]["skills_dir"], config)
    result = writer.write_post(
        topic=topic, platform=platform, content_type=content_type,
        angle=angle, style_samples=h["style"], context=h["context"],
        system_prompt=h["system_prompt"],
    )
    gen_id = _save_generation({
        "type": "post",
        "topic": topic,
        "platform": platform,
        "content_type": content_type,
        "angle": angle,
        "result": result,
    })
    return {"result": result, "id": gen_id}


@app.post("/api/hooks")
async def api_hooks(
    topic: str = Form(...),
    platform: str = Form("telegram"),
    count: int = Form(5),
    patterns: str = Form(""),
):
    h = _get_helpers()
    writer = HookWriter(llm, config["paths"]["skills_dir"], config)
    result = writer.write_hooks(
        topic=topic, platform=platform, count=count,
        patterns=patterns.split(",") if patterns else None,
        style_samples=h["style"], context=h["context"],
    )
    return {"result": result}


@app.post("/api/carousel")
async def api_carousel(
    topic: str = Form(...),
    platform: str = Form("instagram"),
    slide_count: int = Form(10),
    format_type: str = Form("listicle"),
    generate_images: bool = Form(False),
    design_style: str = Form("dark_modern"),
):
    h = _get_helpers()
    writer = CarouselWriter(llm, config["paths"]["skills_dir"], config)
    carousel = writer.write_carousel(
        topic=topic, platform=platform, slide_count=slide_count,
        format_type=format_type, style_samples=h["style"],
        context=h["context"], system_prompt=h["system_prompt"],
    )
    images = []
    if generate_images:
        images = writer.render_carousel_images(
            carousel, output_dir=config["paths"]["output"],
            design_style=design_style,
        )
    return {"carousel": carousel, "images": images}


@app.post("/api/research")
async def api_research(topic: str = Form(...)):
    researcher = Researcher(llm, config)
    topics = researcher.search_viral_topics(topic=topic)
    return {"topics": topics}


@app.post("/api/repurpose")
async def api_repurpose(
    content: str = Form(...),
    platforms: str = Form(""),
    formats: str = Form(""),
):
    h = _get_helpers()
    repurposer = ContentRepurposer(llm, config["paths"]["skills_dir"], config)
    result = repurposer.repurpose(
        source_content=content,
        target_platforms=platforms.split(",") if platforms else None,
        target_formats=formats.split(",") if formats else None,
        style_samples=h["style"], context=h["context"],
    )
    return {"result": result}


@app.post("/api/save-context")
async def api_save_context(content: str = Form(...)):
    p = Path(config["paths"]["context_file"])
    p.write_text(content, encoding="utf-8")
    return {"ok": True}


@app.post("/api/save-system-prompt")
async def api_save_system_prompt(content: str = Form(...)):
    p = Path(config["paths"]["system_prompt"])
    p.write_text(content, encoding="utf-8")
    return {"ok": True}


@app.post("/api/upload-style-sample")
async def api_upload_style_sample(file: UploadFile = File(...)):
    p = Path(config["paths"]["style_samples"]) / file.filename
    content = await file.read()
    p.write_bytes(content)
    return {"ok": True, "filename": file.filename}


@app.get("/api/style-samples")
async def api_list_style_samples():
    p = Path(config["paths"]["style_samples"])
    files = []
    if p.exists():
        for f in sorted(p.iterdir()):
            if f.is_file() and f.suffix in (".txt", ".md"):
                files.append({"name": f.name, "content": f.read_text(encoding="utf-8")[:2000]})
    return {"files": files}


@app.get("/api/generations")
async def api_list_generations():
    """List all saved generations, newest first."""
    entries = _load_generations()
    entries.reverse()
    return {"generations": entries}


@app.delete("/api/generations/{gen_id}")
async def api_delete_generation(gen_id: int):
    """Delete a specific generation by ID."""
    entries = _load_generations()
    new_entries = [e for e in entries if e.get("id") != gen_id]
    if len(new_entries) == len(entries):
        return JSONResponse({"ok": False, "error": "not found"}, status_code=404)
    with open(GENERATIONS_LOG, "w", encoding="utf-8") as f:
        for e in new_entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    return {"ok": True}


@app.delete("/api/generations")
async def api_delete_all_generations():
    """Delete all generations."""
    if GENERATIONS_LOG.exists():
        GENERATIONS_LOG.write_text("")
    return {"ok": True}


def run(host: str = "0.0.0.0", port: int = 8000):
    import uvicorn
    uvicorn.run(app, host=host, port=port)
