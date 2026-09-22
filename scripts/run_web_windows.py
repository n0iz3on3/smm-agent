"""Windows autostart entry point for the SMM Agent web UI.

Run with pythonw.exe (no console window), e.g. via Task Scheduler at logon:
    pythonw.exe scripts\run_web_windows.py

- Serves on http://127.0.0.1:8000
- Writes logs to data/output/webserver.log
- If the server is already running and healthy, exits quietly (safe re-runs)
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import httpx

HOST = "127.0.0.1"
PORT = 8000
BASE = f"http://{HOST}:{PORT}"
LOG_PATH = PROJECT_ROOT / "data" / "output" / "webserver.log"


def already_running() -> bool:
    """True if a healthy SMM Agent web UI already answers on BASE."""
    try:
        r = httpx.get(BASE + "/", timeout=3)
        return r.status_code == 200 and "SMM Agent" in r.text
    except Exception:
        return False


def main() -> int:
    if already_running():
        return 0

    import logging

    import uvicorn

    from src.web.app import app

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=str(LOG_PATH),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("smm-agent.autostart").info("starting web UI at %s", BASE)

    try:
        # log_config=None -> uvicorn loggers propagate to root (file above)
        uvicorn.run(app, host=HOST, port=PORT, log_config=None)
    except OSError as e:
        logging.getLogger("smm-agent.autostart").error(
            "failed to start (port busy by another process?): %s", e
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
