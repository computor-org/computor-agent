"""Tests for ComputorWebSocket connect/liveness behavior."""

import asyncio
import json

import pytest

import computor_agent.tutor.websocket.client as client_module
from computor_agent.tutor.websocket.client import (
    ComputorWebSocket,
    WebSocketConnectionError,
    WebSocketError,
)


class FakeProtocol:
    """Stand-in for the websockets client protocol."""

    def __init__(self, greeting=None, send_error=None):
        self.sent: list[str] = []
        self.closed = False
        self._greeting = greeting or json.dumps(
            {"type": "system:connected", "user_id": "agent-1"}
        )
        self._send_error = send_error

    async def recv(self):
        return self._greeting

    async def send(self, data):
        if self._send_error:
            raise self._send_error
        self.sent.append(data)

    async def close(self):
        self.closed = True


def make_client() -> ComputorWebSocket:
    return ComputorWebSocket(base_url="http://backend.example", token="tok")


def patch_connect(monkeypatch, fake_connect):
    monkeypatch.setattr(client_module.websockets, "connect", fake_connect)


async def test_connect_failure_raises(monkeypatch):
    async def refused(*args, **kwargs):
        raise OSError(111, "Connection refused")

    patch_connect(monkeypatch, refused)
    ws = make_client()

    with pytest.raises(WebSocketConnectionError):
        await ws.connect()
    assert not ws.is_connected


async def test_connect_timeout_raises(monkeypatch):
    async def hangs(*args, **kwargs):
        raise asyncio.TimeoutError()

    patch_connect(monkeypatch, hangs)
    ws = make_client()

    with pytest.raises(WebSocketConnectionError):
        await ws.connect()
    assert not ws.is_connected


async def test_connect_never_wedges(monkeypatch):
    """Regression: the old connect() kept a cumulative reconnect counter that
    was only reset on success. After 10 lifetime failures every further call
    silently returned unconnected, permanently wedging the agent. Every
    failing attempt must raise, no matter how many came before."""
    attempts = 0

    async def refused(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        raise OSError(111, "Connection refused")

    patch_connect(monkeypatch, refused)
    ws = make_client()

    for _ in range(15):
        with pytest.raises(WebSocketConnectionError):
            await ws.connect()
        assert not ws.is_connected

    assert attempts == 15  # one real attempt per call, never a silent no-op


async def test_connect_success_consumes_greeting(monkeypatch):
    protocol = FakeProtocol()

    async def ok(*args, **kwargs):
        return protocol

    patch_connect(monkeypatch, ok)
    ws = make_client()

    await ws.connect()
    try:
        assert ws.is_connected
        assert ws.user_id == "agent-1"
        assert ws._ping_task is not None and not ws._ping_task.done()
    finally:
        await ws.disconnect()
    assert protocol.closed
    assert not ws.is_connected


async def test_connect_enables_protocol_keepalive(monkeypatch):
    captured = {}

    async def ok(*args, **kwargs):
        captured.update(kwargs)
        return FakeProtocol()

    patch_connect(monkeypatch, ok)
    ws = make_client()

    await ws.connect()
    try:
        assert captured["ping_interval"] == 20.0
        assert captured["ping_timeout"] == 20.0
    finally:
        await ws.disconnect()


async def test_connection_lost_during_greeting_raises(monkeypatch):
    class DroppingProtocol(FakeProtocol):
        async def recv(self):
            raise OSError("connection reset by peer")

    protocol = DroppingProtocol()

    async def ok(*args, **kwargs):
        return protocol

    patch_connect(monkeypatch, ok)
    ws = make_client()

    with pytest.raises(WebSocketConnectionError):
        await ws.connect()
    assert not ws.is_connected
    assert protocol.closed


async def test_send_failure_marks_disconnected(monkeypatch):
    protocol = FakeProtocol(send_error=OSError("broken pipe"))

    async def ok(*args, **kwargs):
        return protocol

    patch_connect(monkeypatch, ok)
    ws = make_client()
    await ws.connect()
    try:
        with pytest.raises(WebSocketError):
            await ws.send_ping()
        assert not ws.is_connected
    finally:
        await ws.disconnect()


async def test_activity_watchdog_closes_dead_connection(monkeypatch):
    """Half-open connection: pings keep 'succeeding' but nothing ever comes
    back. The watchdog must force-close so the receive loop can unblock."""
    monkeypatch.setattr(client_module, "PING_INTERVAL", 0.01)
    monkeypatch.setattr(client_module, "ACTIVITY_TIMEOUT", 0.05)

    protocol = FakeProtocol()

    async def ok(*args, **kwargs):
        return protocol

    patch_connect(monkeypatch, ok)
    ws = make_client()
    await ws.connect()
    try:
        async def wait_closed():
            while not protocol.closed:
                await asyncio.sleep(0.01)

        await asyncio.wait_for(wait_closed(), timeout=2.0)
        assert protocol.closed
        assert not ws.is_connected
        assert any("system:ping" in frame for frame in protocol.sent)
    finally:
        await ws.disconnect()
