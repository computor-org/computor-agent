"""Periodic liveness probe for the LLM provider.

Pings the configured LLM in the background and records the result on
the shared MetricsCollector so the dashboard can render the current
state. Prefers a lightweight `list_models()` call (an OpenAI-compatible
GET /models) when available; falls back to a real `check_health()`
completion otherwise.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional

from computor_agent.api.metrics import MetricsCollector

logger = logging.getLogger(__name__)


class LLMHealthMonitor:
    def __init__(
        self,
        provider: Any,
        metrics: MetricsCollector,
        interval_seconds: float = 30.0,
    ) -> None:
        self._provider = provider
        self._metrics = metrics
        self._interval = max(1.0, float(interval_seconds))
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop.clear()
        # Probe immediately so the dashboard isn't blank for the first interval.
        await self._probe()
        self._task = asyncio.create_task(self._loop(), name="llm-health-monitor")

    async def stop(self) -> None:
        self._stop.set()
        task = self._task
        self._task = None
        if task is not None:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

    async def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._interval)
                return  # stop event fired during the wait
            except asyncio.TimeoutError:
                pass
            await self._probe()

    async def _probe(self) -> None:
        start = time.monotonic()
        ok = True
        err: Optional[str] = None
        try:
            if hasattr(self._provider, "list_models"):
                await self._provider.list_models()
            else:
                await self._provider.check_health()
        except Exception as e:
            ok = False
            err = f"{type(e).__name__}: {e}"
            logger.warning(f"LLM probe failed: {err}")
        latency_ms = int((time.monotonic() - start) * 1000)
        self._metrics.llm_probed(ok=ok, latency_ms=latency_ms, error=err)
