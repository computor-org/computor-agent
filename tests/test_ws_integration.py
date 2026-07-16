"""End-to-end reconnect tests against a real websockets server.

These prove the long-uptime bug is gone: the agent must survive an outage
longer than the old 10-attempt budget and reconnect on its own.
"""

import asyncio
import json

import pytest
import websockets

import computor_agent.tutor.websocket.client as client_module
from computor_agent.tutor.websocket.client import ComputorWebSocket
from computor_agent.tutor.websocket.scheduler import WebSocketScheduler

pytestmark = pytest.mark.integration


class FakeBackend:
    """Minimal WebSocket server speaking the computor greeting protocol."""

    def __init__(self):
        self.server = None
        self.port = None
        self.connections = []
        self.answer_pings = True

    async def handler(self, ws):
        self.connections.append(ws)
        await ws.send(json.dumps({"type": "system:connected", "user_id": "agent-1"}))
        try:
            async for raw in ws:
                msg = json.loads(raw)
                if msg.get("type") == "system:ping" and self.answer_pings:
                    await ws.send(json.dumps({"type": "system:pong"}))
        except websockets.ConnectionClosed:
            pass

    async def start(self, port=0):
        self.server = await websockets.serve(self.handler, "127.0.0.1", port)
        self.port = self.server.sockets[0].getsockname()[1]

    async def stop(self):
        # Close the listener first so no new connections slip in, then drop
        # the established ones (Server.close() alone does not reliably close
        # live connections across websockets versions).
        self.server.close()
        await self.kick_all()
        await self.server.wait_closed()

    async def kick_all(self, code=1012):
        for ws in list(self.connections):
            await ws.close(code=code)
        self.connections.clear()


async def wait_until(predicate, timeout=10.0, interval=0.02):
    async def loop():
        while not predicate():
            await asyncio.sleep(interval)

    await asyncio.wait_for(loop(), timeout=timeout)


def make_scheduler(ws) -> WebSocketScheduler:
    scheduler = WebSocketScheduler(
        client=object(),
        ws=ws,
        reconnect_delay_seconds=0.01,
    )

    async def no_unread():
        pass

    async def no_courses():
        scheduler._course_ids = []

    scheduler._process_unread_messages = no_unread
    scheduler._discover_courses = no_courses
    return scheduler


async def test_connect_against_real_server():
    backend = FakeBackend()
    await backend.start()
    try:
        ws = ComputorWebSocket(f"http://127.0.0.1:{backend.port}", token="t")
        await ws.connect()
        try:
            assert ws.is_connected
            assert ws.user_id == "agent-1"
        finally:
            await ws.disconnect()
        assert not ws.is_connected
    finally:
        await backend.stop()


async def test_scheduler_reconnects_after_force_close():
    backend = FakeBackend()
    await backend.start()
    ws = ComputorWebSocket(f"http://127.0.0.1:{backend.port}", token="t")
    scheduler = make_scheduler(ws)

    start_task = asyncio.create_task(scheduler.start())
    try:
        await wait_until(lambda: ws.is_connected)

        await backend.kick_all()

        # A new server-side connection proves the scheduler reconnected
        await wait_until(lambda: backend.connections and ws.is_connected)
    finally:
        await scheduler.stop()
        start_task.cancel()
        try:
            await start_task
        except asyncio.CancelledError:
            pass
        await backend.stop()


async def test_scheduler_survives_outage_longer_than_old_budget():
    """THE regression test for the reported production bug: before the fix,
    10 failed attempts permanently wedged the client and the agent never
    reconnected without a manual restart. Here the backend stays down for
    more than 12 attempts, then comes back — the agent must recover."""
    backend = FakeBackend()
    await backend.start()
    port = backend.port

    ws = ComputorWebSocket(f"http://127.0.0.1:{port}", token="t")
    attempts = {"count": 0}
    original_connect = ws.connect

    async def counting_connect():
        attempts["count"] += 1
        await original_connect()

    ws.connect = counting_connect

    scheduler = make_scheduler(ws)
    start_task = asyncio.create_task(scheduler.start())
    try:
        await wait_until(lambda: ws.is_connected)
        attempts["count"] = 0

        # Total outage: the server goes away entirely
        await backend.stop()

        # Let the scheduler fail past the old 10-attempt budget
        await wait_until(lambda: attempts["count"] >= 12, timeout=30.0)
        assert not ws.is_connected

        # Backend comes back on the same port
        await backend.start(port=port)

        await wait_until(lambda: ws.is_connected, timeout=30.0)
        assert backend.connections
    finally:
        await scheduler.stop()
        start_task.cancel()
        try:
            await start_task
        except asyncio.CancelledError:
            pass
        await backend.stop()


async def test_watchdog_recovers_from_silent_server(monkeypatch):
    """Half-open simulation: the server stops answering application pings and
    sends nothing. The activity watchdog must force-close so the scheduler
    reconnects instead of blocking on receive() forever."""
    monkeypatch.setattr(client_module, "PING_INTERVAL", 0.05)
    monkeypatch.setattr(client_module, "ACTIVITY_TIMEOUT", 0.2)

    backend = FakeBackend()
    await backend.start()
    ws = ComputorWebSocket(f"http://127.0.0.1:{backend.port}", token="t")
    scheduler = make_scheduler(ws)

    start_task = asyncio.create_task(scheduler.start())
    try:
        await wait_until(lambda: ws.is_connected)
        first_connection = backend.connections[0]

        # Server goes silent: pings are swallowed, nothing is sent. The
        # reconnect happens within milliseconds, so don't poll for the
        # transient disconnected state — a NEW server-side connection is the
        # durable proof that the watchdog killed the silent one and the
        # scheduler reconnected.
        backend.answer_pings = False
        await wait_until(
            lambda: any(c is not first_connection for c in backend.connections),
            timeout=10.0,
        )

        # Let the server answer again; the connection must stabilize
        backend.answer_pings = True
        await wait_until(lambda: ws.is_connected, timeout=10.0)
    finally:
        await scheduler.stop()
        start_task.cancel()
        try:
            await start_task
        except asyncio.CancelledError:
            pass
        await backend.stop()
