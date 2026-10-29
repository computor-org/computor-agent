"""A WebSocket outage must not cost a student their answer.

Posting a reply, listing unread messages and acking them all go over REST; the
WebSocket only carries wake-up events, typing indicators and read-marks. Yet a
socket that dropped between the unread scan and the processing of an entry used
to abort that entry outright — `subscribe()` is the one client call that raises
while disconnected rather than no-op'ing, and it was awaited unguarded just to
enable a typing dot.

The fallout compounded: the abort ran through `_record_failure`, which counted
an attempt toward the permanent park at MAX_MESSAGE_ATTEMPTS and stamped
`last_processed`, putting the whole submission group into cooldown. A handful of
reconnects during one lecture could therefore park a question until the next
restart, and every scan in between logged it as "in cooldown".
"""

from datetime import datetime, timedelta

from computor_agent.tutor.websocket.client import WebSocketError
from computor_agent.tutor.websocket.scheduler import (
    MAX_MESSAGE_ATTEMPTS,
    WebSocketScheduler,
)


class FakeWS:
    """Stand-in for ComputorWebSocket, healthy unless told otherwise."""

    def __init__(self, connected=True):
        self.is_connected = connected
        self.subscribed: list[str] = []
        self.marked_read: list[tuple[str, str]] = []
        self.typing_events: list[tuple[str, str]] = []

    async def subscribe(self, channels):
        if not self.is_connected:
            raise WebSocketError("Not connected")
        self.subscribed.extend(channels)

    async def mark_read(self, channel, message_id):
        if not self.is_connected:
            return  # the real client silently no-ops while disconnected
        self.marked_read.append((channel, message_id))

    async def send_typing_start(self, channel):
        if not self.is_connected:
            raise WebSocketError("Not connected")
        self.typing_events.append(("start", channel))

    async def send_typing_stop(self, channel):
        if not self.is_connected:
            raise WebSocketError("Not connected")
        self.typing_events.append(("stop", channel))


class DyingTypingStopWS(FakeWS):
    """Connected, but the link dies just as the answer finishes posting."""

    async def send_typing_stop(self, channel):
        raise WebSocketError("Connection closed while sending")


class FakeMessages:
    def __init__(self):
        self.reads_called: list[str] = []

    async def reads(self, id):
        self.reads_called.append(id)


class FakeClient:
    def __init__(self):
        self.messages = FakeMessages()


class FakeMessage:
    def __init__(self, id, content="hello @tutor", title="Question", author_id="student-1"):
        self.id = id
        self.content = content
        self.title = title
        self.author_id = author_id


def make_scheduler(ws, client=None):
    calls: list[str] = []

    async def on_trigger(result, course_content, channel):
        calls.append(result.message_trigger.message_id)

    scheduler = WebSocketScheduler(
        client=client or FakeClient(),
        ws=ws,
        on_message_trigger=on_trigger,
        cooldown_seconds=60,
    )
    return scheduler, calls


async def _process(scheduler, message_id="msg-1", group="sg-1"):
    return await scheduler._process_trigger_entries(
        "course-1", [(FakeMessage(id=message_id), group, None)]
    )


async def test_message_is_answered_while_the_socket_is_down():
    """The reply travels over REST, so a dead socket must not block it."""
    ws = FakeWS(connected=False)
    scheduler, calls = make_scheduler(ws)

    count = await _process(scheduler)

    assert count == 1
    assert calls == ["msg-1"]
    assert ws.subscribed == []  # no typing channel, and no exception either


async def test_read_mark_falls_back_to_rest_while_disconnected():
    """Otherwise an answered message stays unread forever: `last_message_id`
    skips it on every later scan while it keeps occupying a slot under the
    unread per-page cap."""
    ws = FakeWS(connected=False)
    client = FakeClient()
    scheduler, _ = make_scheduler(ws, client=client)

    await _process(scheduler)

    assert ws.marked_read == []
    assert client.messages.reads_called == ["msg-1"]
    assert scheduler._get_or_create_state("sg-1").last_message_id == "msg-1"


async def test_outage_does_not_record_a_failure():
    """A dead socket says nothing about the message, so nothing to back off."""
    ws = FakeWS(connected=False)
    scheduler, _ = make_scheduler(ws)

    await _process(scheduler)

    assert scheduler._failures == {}


async def test_a_flapping_socket_never_parks_a_question():
    """Transport deferrals are uncounted: MAX_MESSAGE_ATTEMPTS reconnects in a
    row must still leave the message eligible."""
    scheduler, _ = make_scheduler(FakeWS())
    state = scheduler._get_or_create_state("sg-1")

    for _ in range(MAX_MESSAGE_ATTEMPTS + 3):
        scheduler._record_failure(
            "msg-1", state, WebSocketError("Not connected"), transient=True
        )

    failure = scheduler._failures["msg-1"]
    assert failure.attempts == 0
    assert not failure.parked
    # Retry is due in seconds, not the escalating 30s..15min failure backoff.
    assert failure.retry_after - datetime.now() < timedelta(seconds=30)
    # And the group is not dragged into cooldown by a transport problem.
    assert state.last_processed is None
    assert scheduler._should_skip("sg-1") is False


async def test_typing_stop_failure_does_not_duplicate_the_answer():
    """`stop_typing` runs in the typing context manager's `finally`, after the
    reply is posted. Letting it raise marked a delivered answer as failed, which
    skipped the `last_message_id` bookkeeping and re-sent it on the next scan."""
    ws = DyingTypingStopWS()
    scheduler, calls = make_scheduler(ws)

    count = await _process(scheduler)

    assert count == 1
    assert calls == ["msg-1"]
    assert scheduler._failures == {}
    assert scheduler._get_or_create_state("sg-1").last_message_id == "msg-1"

    # A second scan surfacing the same message must not answer it again.
    assert await _process(scheduler) == 0
    assert calls == ["msg-1"]
