"""Tests for WebSocketScheduler reconnect behavior."""

import asyncio

import pytest

from computor_agent.tutor.errors import AuthFatalError
from computor_agent.tutor.websocket.client import (
    WebSocketConnectionError,
    WebSocketError,
)
from computor_agent.tutor.websocket.scheduler import WebSocketScheduler


class FakeWS:
    """Stand-in for ComputorWebSocket with scriptable connect behavior."""

    def __init__(self, fail_connects=0, connect_silently_noop=False):
        self.fail_connects = fail_connects
        self.connect_silently_noop = connect_silently_noop
        self.connect_calls = 0
        self.disconnect_calls = 0
        self.is_connected = False
        self.token = None
        self.user_id = "agent-1"

    async def connect(self):
        self.connect_calls += 1
        if self.connect_silently_noop:
            # Old-wedge behavior: return without connecting and without raising
            return
        if self.connect_calls <= self.fail_connects:
            raise WebSocketConnectionError("Connection refused")
        self.is_connected = True

    async def disconnect(self):
        self.disconnect_calls += 1
        self.is_connected = False

    def update_token(self, token):
        self.token = token

    async def subscribe(self, channels):
        if not self.is_connected:
            raise WebSocketError("Not connected")


def make_scheduler(ws, **kwargs):
    kwargs.setdefault("reconnect_delay_seconds", 0.001)
    scheduler = WebSocketScheduler(client=object(), ws=ws, **kwargs)
    scheduler._running = True

    unread_calls = []

    async def fake_unread():
        unread_calls.append(1)

    scheduler._process_unread_messages = fake_unread
    return scheduler, unread_calls


async def test_reconnect_succeeds_after_failures():
    ws = FakeWS(fail_connects=3)
    scheduler, unread_calls = make_scheduler(ws)
    scheduler._subscribed_channels.add("submission_group:sg-1")

    result = await asyncio.wait_for(scheduler._reconnect(), timeout=5.0)

    assert result is True
    assert ws.is_connected
    assert ws.connect_calls == 4
    assert ws.disconnect_calls >= 1
    # Stale channels are dropped, not replayed; they re-subscribe lazily
    assert scheduler._subscribed_channels == set()
    assert len(unread_calls) == 1


async def test_silent_noop_connect_is_not_reported_as_success():
    """Regression: the wedged client's connect() returned unconnected without
    raising, and the old _reconnect logged a false 'reconnected successfully'.
    An unconnected socket after connect() must count as a failed attempt."""
    ws = FakeWS(connect_silently_noop=True)
    scheduler, unread_calls = make_scheduler(ws, max_reconnect_attempts=3)

    with pytest.raises(WebSocketError):
        await asyncio.wait_for(scheduler._reconnect(), timeout=5.0)

    assert ws.connect_calls == 3
    assert unread_calls == []


async def test_backoff_is_capped_exponential_with_jitter(monkeypatch):
    delays = []

    async def fake_sleep(delay):
        delays.append(delay)

    monkeypatch.setattr(
        "computor_agent.tutor.websocket.scheduler.asyncio.sleep", fake_sleep
    )

    ws = FakeWS(fail_connects=10**9)
    scheduler, _ = make_scheduler(
        ws, reconnect_delay_seconds=5.0, max_reconnect_attempts=8
    )

    with pytest.raises(WebSocketError):
        await scheduler._reconnect()

    expected_bases = [5, 10, 20, 40, 80, 160, 300, 300]
    assert len(delays) == len(expected_bases)
    for delay, base in zip(delays, expected_bases):
        assert 0.8 * base <= delay <= 1.2 * base


async def test_attempt_limit_raises_instead_of_returning_false():
    ws = FakeWS(fail_connects=10**9)
    scheduler, _ = make_scheduler(ws, max_reconnect_attempts=2)

    with pytest.raises(WebSocketError, match="after 2 attempts"):
        await asyncio.wait_for(scheduler._reconnect(), timeout=5.0)


async def test_auth_exhaustion_raises_auth_fatal():
    """Token provider keeps failing AND the old token no longer connects
    (expired): after MAX_AUTH_FAILURES strikes the loop must raise instead
    of retrying forever or (worse) silently returning False."""

    async def no_token():
        return None

    ws = FakeWS(fail_connects=10**9)  # expired token: server rejects connects
    scheduler, _ = make_scheduler(ws, token_provider=no_token)

    with pytest.raises(AuthFatalError):
        await asyncio.wait_for(scheduler._reconnect(), timeout=5.0)

    # Attempts 1 and 2 still tried the old token; strike 3 raised pre-connect
    assert ws.connect_calls == 2


async def test_token_refresh_failure_still_tries_old_token():
    """A transient refresh outage must not block reconnecting when the old
    token still works, and success resets the failure counter."""

    async def flaky_provider():
        raise RuntimeError("refresh endpoint down")

    ws = FakeWS()
    scheduler, _ = make_scheduler(ws, token_provider=flaky_provider)

    result = await asyncio.wait_for(scheduler._reconnect(), timeout=5.0)

    assert result is True
    assert ws.is_connected
    assert scheduler._consecutive_auth_failures == 0


async def test_token_refresh_applied_on_reconnect():
    tokens = iter(["fresh-token"])

    async def provider():
        return next(tokens)

    ws = FakeWS()
    scheduler, _ = make_scheduler(ws, token_provider=provider)

    result = await asyncio.wait_for(scheduler._reconnect(), timeout=5.0)

    assert result is True
    assert ws.token == "fresh-token"


async def test_stop_during_backoff_returns_false():
    ws = FakeWS(fail_connects=10**9)
    scheduler, _ = make_scheduler(ws, reconnect_delay_seconds=0.2)

    task = asyncio.create_task(scheduler._reconnect())
    await asyncio.sleep(0.05)
    scheduler._running = False

    result = await asyncio.wait_for(task, timeout=5.0)
    assert result is False


async def test_event_loop_reconnects_on_receive_error():
    ws = FakeWS()
    scheduler, unread_calls = make_scheduler(ws)

    receive_calls = {"count": 0}

    def receive():
        receive_calls["count"] += 1

        async def gen():
            if receive_calls["count"] == 1:
                raise WebSocketError("Connection lost")
            scheduler._running = False
            if False:
                yield {}

        return gen()

    ws.receive = receive

    await asyncio.wait_for(scheduler._event_loop(), timeout=5.0)

    assert ws.connect_calls == 1  # one successful reconnect
    assert len(unread_calls) == 1
    assert receive_calls["count"] == 2
