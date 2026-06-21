"""FastAPI web application for SMM Agent."""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
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
app.mount("/output", StaticFiles(directory=str(PROJECT_ROOT / "data" / "output")), name="output")
_templates_dir = str(Path(__file__).parent / "templates")
templates = Jinja2Templates(directory=_templates_dir)

MODEL_NAME = config.get("llm", {}).get("model", "")
GENERATIONS_LOG = Path(config.get("paths", {}).get("generations_log", "./data/generations.jsonl"))
CAROUSELS_LOG = Path(config.get("paths", {}).get("output", "./data/output")) / "carousels.jsonl"


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


def _save_carousel(entry: dict):
    """Append a carousel record to JSONL log."""
    CAROUSELS_LOG.parent.mkdir(parents=True, exist_ok=True)
    # Read current max id
    carousels = _load_carousels()
    next_cid = max((c.get("id", 0) for c in carousels), default=0) + 1
    entry["id"] = next_cid
    entry["created_at"] = datetime.now(timezone.utc).isoformat()
    with open(CAROUSELS_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return next_cid


def _load_carousels() -> list[dict]:
    """Load all saved carousels."""
    if not CAROUSELS_LOG.exists():
        return []
    entries = []
    with open(CAROUSELS_LOG, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return entries


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
    content_type: str = Form("storytelling"),
    angle: str = Form(""),
    platform: str = Form("auto"),
):
    """Queue a post generation task. GLM agent picks it up via OpenClaw."""
    import uuid
    task_id = str(uuid.uuid4())[:8]

    # Write to queue
    queue_path = Path(config["paths"]["output"]) / "queue.jsonl"
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    task = {
        "task_id": task_id,
        "topic": topic,
        "platform": platform,
        "content_type": content_type,
        "angle": angle,
    }
    with open(queue_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(task, ensure_ascii=False) + "\n")

    # Trigger OpenClaw wake
    try:
        import subprocess
        subprocess.Popen(
            ["curl", "-s", "-X", "POST",
             "http://127.0.0.1:18790/api/wake",
             "-H", "Authorization: Bearer 8971c53ccecc7cedfa0ff7d6467cf8ddd603755a5d048005",
             "-H", "Content-Type: application/json",
             "-d", json.dumps({"text": f"SMM queue: new task {task_id} — {topic}"})],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass

    return {"status": "queued", "task_id": task_id, "topic": topic}


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
):
    """Step 1: Generate movie carousel text (topics + caption + film list).

    Returns carousel data WITHOUT images. User must confirm before
    calling /api/carousel/render to generate PNG slides.
    """
    h = _get_helpers()
    writer = CarouselWriter(llm, config["paths"]["skills_dir"], config)

    # Try up to 3 times to get a valid carousel with slides
    carousel = None
    for attempt in range(3):
        carousel = writer.generate_movie_carousel(
            topic=topic,
            style_samples=h["style"],
            context=h["context"],
            system_prompt=h["system_prompt"],
        )
        slides = carousel.get("slides", [])
        if slides and len(slides) >= 2 and not "raw" in carousel:
            break
        print(f"Carousel attempt {attempt+1}: got {len(slides)} slides, retrying...")

    # Resolve real Russian titles from Kinopoisk
    if carousel.get("slides"):
        try:
            carousel["slides"] = CarouselWriter.resolve_russian_titles(carousel["slides"])
        except Exception as e:
            print(f"Warning: failed to resolve Russian titles: {e}")

    # Final validation
    if not carousel.get("slides") or len(carousel.get("slides", [])) == 0:
        return JSONResponse({
            "error": "Не удалось сгенерировать карусель. Попробуйте ещё раз.",
            "carousel": {"slides": [], "selected_topic": topic, "caption": ""},
            "images": [],
            "caption": "",
        }, status_code=200)

    return {
        "carousel": carousel,
        "images": [],
        "caption": carousel.get("caption", ""),
    }


@app.post("/api/carousel/correct")
async def api_carousel_correct(
    topic: str = Form(""),
    correction: str = Form(""),
    carousel_json: str = Form("{}"),
):
    """Apply user corrections to existing carousel data.

    Receives current carousel + correction text, asks LLM to modify.
    """
    try:
        current = json.loads(carousel_json)
    except json.JSONDecodeError:
        return JSONResponse({"error": "Invalid carousel data"}, status_code=400)

    h = _get_helpers()
    writer = CarouselWriter(llm, config["paths"]["skills_dir"], config)

    # Build a focused correction prompt
    slides_text = ""
    for s in current.get("slides", []):
        slides_text += f"{s.get('slide')}. {s.get('title', '')} ({s.get('title_en', '')}, {s.get('year', '')})\n"

    correction_topic = f"Тема: {current.get('selected_topic', topic)}\n\nТекущие фильмы:\n{slides_text}\nИСПРАВЛЕНИЯ: {correction}\n\nВнеси исправления. Ответь в том же JSON формате."

    carousel = writer.generate_movie_carousel(
        topic=correction_topic,
        style_samples=h["style"],
        context=h["context"],
        system_prompt=h["system_prompt"],
    )

    # Resolve Russian titles
    if carousel.get("slides"):
        try:
            carousel["slides"] = CarouselWriter.resolve_russian_titles(carousel["slides"])
        except Exception as e:
            print(f"Warning: failed to resolve Russian titles: {e}")

    if not carousel.get("slides"):
        # Fallback: return original with note
        return {
            "carousel": current,
            "images": [],
            "caption": current.get("caption", ""),
        }

    return {
        "carousel": carousel,
        "images": [],
        "caption": carousel.get("caption", current.get("caption", "")),
    }


@app.post("/api/carousel/render")
async def api_carousel_render(
    carousel_json: str = Form(...),
    topic: str = Form(""),
):
    """Step 2: Generate PNG poster slides from confirmed carousel data.

    Receives the carousel JSON from step 1, searches posters, renders PNGs.
    """
    try:
        carousel = json.loads(carousel_json)
    except json.JSONDecodeError:
        return JSONResponse({"error": "Invalid carousel JSON"}, status_code=400)

    images = []
    slides = carousel.get("slides", [])
    for slide in slides:
        title = slide.get("title", "")
        title_en = slide.get("title_en")
        year = slide.get("year")
        description = slide.get("description", "")

        if not title:
            continue

        poster_bytes = CarouselWriter.search_movie_still(title, year=year, title_en=title_en)
        if not poster_bytes and title_en:
            # Fallback: try with Russian title
            poster_bytes = CarouselWriter.search_movie_still(title, year=year, title_en=None)
        if poster_bytes:
            safe_name = re.sub(r'[^a-zA-Zа-яА-Я0-9]', '_', title)[:40]
            fname = f"poster_{safe_name}_{slide.get('slide', 0)}.png"
            try:
                CarouselWriter.render_poster_slide(
                    poster_bytes=poster_bytes,
                    title=title,
                    year=year,
                    description=description,
                    output_path=config["paths"]["output"],
                    filename=fname,
                )
                images.append(fname)
            except Exception as e:
                print(f"Failed to render slide {slide.get('slide')}/{title}: {e}")

    # Save to carousel history
    carousel_entry = {
        "topic": topic,
        "carousel": carousel,
        "images": images,
        "caption": carousel.get("caption", ""),
    }
    _save_carousel(carousel_entry)

    return {
        "carousel": carousel,
        "images": images,
        "caption": carousel.get("caption", ""),
    }


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


@app.post("/api/generations")
async def api_create_generation(request: Request):
    """Save a pre-generated result (from external agent)."""
    body = await request.json()
    gen_id = _save_generation({
        "type": body.get("type", "post"),
        "topic": body.get("topic", ""),
        "platform": body.get("platform", "threads"),
        "result": body.get("result", ""),
    })
    return {"ok": True, "id": gen_id}


@app.delete("/api/generations")
async def api_delete_all_generations():
    """Delete all generations."""
    if GENERATIONS_LOG.exists():
        GENERATIONS_LOG.write_text("")
    return {"ok": True}


@app.get("/api/carousels")
async def api_list_carousels():
    """List all saved carousels, newest first."""
    entries = _load_carousels()
    entries.reverse()
    return {"carousels": entries}


@app.delete("/api/carousels/{carousel_id}")
async def api_delete_carousel(carousel_id: int):
    """Delete a specific carousel by ID."""
    entries = _load_carousels()
    new_entries = [e for e in entries if e.get("id") != carousel_id]
    if len(new_entries) == len(entries):
        return JSONResponse({"ok": False, "error": "not found"}, status_code=404)
    with open(CAROUSELS_LOG, "w", encoding="utf-8") as f:
        for e in new_entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    return {"ok": True}


@app.get("/api/carousels/download")
async def api_download_carousel_images(files: str = ""):
    """Download carousel images as a ZIP file."""
    import zipfile
    import io as _io

    if not files:
        return JSONResponse({"error": "No files specified"}, status_code=400)

    filenames = [f.strip() for f in files.split(",") if f.strip()]
    output_dir = Path(config["paths"]["output"])

    zip_buffer = _io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname in filenames:
            fpath = output_dir / fname
            if fpath.exists() and fpath.is_file():
                # Security: ensure file is within output dir
                try:
                    fpath.resolve().relative_to(output_dir.resolve())
                except ValueError:
                    continue
                zf.write(fpath, fname)

    if zip_buffer.tell() == 0:
        return JSONResponse({"error": "No valid files found"}, status_code=404)

    zip_buffer.seek(0)
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=carousel.zip"},
    )


def run(host: str = "0.0.0.0", port: int = 8000):
    import uvicorn
    uvicorn.run(app, host=host, port=port)
