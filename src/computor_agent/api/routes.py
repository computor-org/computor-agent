"""Routes for the dashboard API."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from computor_agent.api.metrics import MetricsCollector

TEMPLATE_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))


def build_router(
    *,
    metrics: MetricsCollector,
    scheduler,
    log_file: Optional[str],
) -> APIRouter:
    router = APIRouter()

    def _scheduler_stats() -> dict:
        try:
            return scheduler.get_stats()
        except Exception:
            return {
                "running": False,
                "connected": False,
                "courses": 0,
                "tracked_groups": 0,
                "active_typing": 0,
            }

    @router.get("/health")
    def health() -> dict:
        s = _scheduler_stats()
        running = bool(s.get("running"))
        connected = bool(s.get("connected"))
        return {
            "status": "ok" if running and connected else "degraded",
            "scheduler_running": running,
            "ws_connected": connected,
            "started_at": metrics.started_at,
        }

    @router.get("/metrics")
    def metrics_endpoint() -> dict:
        return {
            "scheduler": _scheduler_stats(),
            "agent": metrics.snapshot(),
        }

    @router.get("/logs")
    def logs(tail: int = Query(200, ge=1, le=5000)) -> dict:
        if not log_file:
            return {"log_file": None, "lines": []}
        try:
            return {"log_file": log_file, "lines": _tail_file(log_file, tail)}
        except FileNotFoundError:
            return {"log_file": log_file, "lines": [], "error": "file not found"}

    @router.get("/", response_class=HTMLResponse)
    def dashboard(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "scheduler": _scheduler_stats(),
                "agent": metrics.snapshot(),
                "log_file": log_file,
                "log_lines": _tail_file(log_file, 200) if log_file else [],
            },
        )

    return router


def _tail_file(path: str, n: int) -> list[str]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(path)
    chunk = 64 * 1024
    with p.open("rb") as f:
        f.seek(0, 2)
        size = f.tell()
        f.seek(max(0, size - chunk))
        data = f.read()
    text = data.decode("utf-8", errors="replace")
    lines = text.splitlines()
    return lines[-n:]
