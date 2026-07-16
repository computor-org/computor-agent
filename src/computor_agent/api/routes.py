"""Routes for the dashboard API."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query, Request, Response
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

    @router.get("/healthz")
    def healthz(response: Response) -> dict:
        """Strict liveness probe for container orchestration.

        HTTP 200 only when the scheduler is running and the WebSocket is
        connected; 503 otherwise. LLM state is deliberately ignored:
        restarting the container cannot fix an LLM outage and the agent
        retries LLM calls on its own (see /health for the full picture).
        """
        s = _scheduler_stats()
        running = bool(s.get("running"))
        connected = bool(s.get("connected"))
        healthy = running and connected
        response.status_code = 200 if healthy else 503
        return {
            "status": "ok" if healthy else "unavailable",
            "scheduler_running": running,
            "ws_connected": connected,
        }

    @router.get("/health")
    def health() -> dict:
        s = _scheduler_stats()
        running = bool(s.get("running"))
        connected = bool(s.get("connected"))
        llm_available = metrics.llm.available  # None | True | False
        llm_ok = llm_available is not False  # treat unknown (None) as not-yet-failed
        return {
            "status": "ok" if (running and connected and llm_ok) else "degraded",
            "scheduler_running": running,
            "ws_connected": connected,
            "llm_available": llm_available,
            "llm_provider": metrics.llm.provider,
            "llm_model": metrics.llm.model,
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
        # Starlette ≥0.28 expects (request, name, context); the old
        # (name, context-with-request) form raises "unhashable type: 'dict'"
        # because Jinja2 tries to use the context dict as a template lookup key.
        return templates.TemplateResponse(
            request,
            "dashboard.html",
            {
                "scheduler": _scheduler_stats(),
                "agent": metrics.snapshot(),
                "log_file": log_file,
                "log_lines": log_buffer.tail(200),
            },
        )

    return router
