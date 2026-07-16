"""Tests for the dashboard API routes (health endpoints)."""

import pytest

fastapi = pytest.importorskip("fastapi")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from computor_agent.api.log_buffer import LogBuffer
from computor_agent.api.metrics import MetricsCollector
from computor_agent.api.routes import build_router


class StubScheduler:
    def __init__(self, running=True, connected=True):
        self.running = running
        self.connected = connected

    def get_stats(self):
        return {
            "running": self.running,
            "connected": self.connected,
            "courses": 1,
            "tracked_groups": 0,
            "active_typing": [],
        }


def make_client(scheduler) -> TestClient:
    app = FastAPI()
    app.include_router(
        build_router(
            metrics=MetricsCollector(),
            scheduler=scheduler,
            log_buffer=LogBuffer(),
        )
    )
    return TestClient(app)


def test_healthz_ok_when_running_and_connected():
    client = make_client(StubScheduler(running=True, connected=True))
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.parametrize(
    "running,connected", [(True, False), (False, True), (False, False)]
)
def test_healthz_503_when_unhealthy(running, connected):
    client = make_client(StubScheduler(running=running, connected=connected))
    response = client.get("/healthz")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unavailable"
    assert body["scheduler_running"] is running
    assert body["ws_connected"] is connected


def test_healthz_ignores_llm_state():
    """An LLM outage must not flip /healthz — restarting the container
    cannot fix the LLM, and the agent retries LLM calls on its own."""
    scheduler = StubScheduler(running=True, connected=True)
    metrics = MetricsCollector()
    metrics.llm.available = False

    app = FastAPI()
    app.include_router(
        build_router(metrics=metrics, scheduler=scheduler, log_buffer=LogBuffer())
    )
    client = TestClient(app)

    assert client.get("/healthz").status_code == 200
    # The informational /health endpoint still reports degraded
    assert client.get("/health").json()["status"] == "degraded"


def test_health_stays_informational_200():
    client = make_client(StubScheduler(running=False, connected=False))
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
