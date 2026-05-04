"""FastAPI app + uvicorn launcher for the dashboard."""

from __future__ import annotations

import logging
from typing import Optional

import uvicorn
from fastapi import FastAPI

from computor_agent.api.log_buffer import LogBuffer
from computor_agent.api.metrics import MetricsCollector
from computor_agent.api.routes import build_router

logger = logging.getLogger(__name__)


def create_app(
    *,
    metrics: MetricsCollector,
    scheduler,
    log_buffer: LogBuffer,
    log_file: Optional[str] = None,
) -> FastAPI:
    app = FastAPI(
        title="Computor Tutor Agent",
        docs_url="/api/docs",
        redoc_url=None,
    )
    app.include_router(
        build_router(
            metrics=metrics,
            scheduler=scheduler,
            log_buffer=log_buffer,
            log_file=log_file,
        )
    )
    return app


class APIServer:
    """Run uvicorn inside the agent's event loop with cooperative shutdown."""

    def __init__(self, app: FastAPI, host: str, port: int) -> None:
        config = uvicorn.Config(
            app,
            host=host,
            port=port,
            log_level="info",
            access_log=False,
            lifespan="off",
        )
        self._server = uvicorn.Server(config)
        # The CLI manages SIGINT/SIGTERM; uvicorn's own handlers would
        # otherwise race with the agent's shutdown path.
        self._server.install_signal_handlers = lambda: None
        self.host = host
        self.port = port

    async def serve(self) -> None:
        logger.info(f"Dashboard listening on http://{self.host}:{self.port}")
        await self._server.serve()

    async def stop(self) -> None:
        self._server.should_exit = True
