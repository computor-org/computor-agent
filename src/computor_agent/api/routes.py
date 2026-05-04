"""Routes for the dashboard API."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from computor_agent.api.log_buffer import LogBuffer
from computor_agent.api.metrics import MetricsCollector

TEMPLATE_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))


def build_router(
    *,
    metrics: MetricsCollector,
    scheduler,
    log_buffer: LogBuffer,
    log_file: Optional[str] = None,
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
        return {
            "log_file": log_file,
            "lines": log_buffer.tail(tail),
            "buffer_size": len(log_buffer),
        }

    @router.get("/", response_class=HTMLResponse)
    def dashboard(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "scheduler": _scheduler_stats(),
                "agent": metrics.snapshot(),
                "log_file": log_file,
                "log_lines": log_buffer.tail(200),
            },
        )

    return router
