"""Tests for the WebSocket scheduler's trigger-entry processing."""

from computor_agent.tutor.websocket.scheduler import WebSocketScheduler


class FakeWS:
    """Minimal stand-in for ComputorWebSocket used by the processing path."""

    def __init__(self):
        self.subscribed: list[str] = []
        self.marked_read: list[tuple[str, str]] = []
        self.typing_events: list[tuple[str, str]] = []

    async def subscribe(self, channels):
        self.subscribed.extend(channels)

    async def mark_read(self, channel, message_id):
        self.marked_read.append((channel, message_id))

    async def send_typing_start(self, channel):
        self.typing_events.append(("start", channel))

    async def send_typing_stop(self, channel):
        self.typing_events.append(("stop", channel))


class ExplodingSubscribeWS(FakeWS):
    """Raises when subscribing to a channel of the poisoned submission group."""

    async def subscribe(self, channels):
        if any("sg-bad" in channel for channel in channels):
            raise RuntimeError("subscribe boom")
        await super().subscribe(channels)


class FakeMessage:
    def __init__(self, id, content="hello @tutor", title="Question", author_id="student-1"):
        self.id = id
        self.content = content
        self.title = title
        self.author_id = author_id


def make_scheduler(ws=None):
    triggers = []

    async def on_trigger(result, course_content, channel):
        triggers.append((result, course_content, channel))

    scheduler = WebSocketScheduler(
        client=object(),
        ws=ws or FakeWS(),
        on_message_trigger=on_trigger,
        cooldown_seconds=0,
    )
    return scheduler, triggers


async def test_process_trigger_entries_invokes_callback():
    """Regression: an undefined `title` variable raised NameError for every
    trigger batch and was silently swallowed, so no message was ever
    processed."""
    ws = FakeWS()
    scheduler, triggers = make_scheduler(ws=ws)
    msg = FakeMessage(id="msg-1")

    count = await scheduler._process_trigger_entries("course-1", [(msg, "sg-1", None)])

    assert count == 1
    assert len(triggers) == 1
    result, course_content, channel = triggers[0]
    assert course_content is None
    assert channel == "submission_group:sg-1"
    trigger = result.message_trigger
    assert trigger.message_id == "msg-1"
    assert trigger.title == "Question"
    assert trigger.content == "hello @tutor"
    assert trigger.is_follow_up is False
    assert ws.marked_read == [("submission_group:sg-1", "msg-1")]
    assert scheduler._get_or_create_state("sg-1").last_message_id == "msg-1"


async def test_process_trigger_entries_follow_up_keeps_thread_root():
    scheduler, triggers = make_scheduler()
    msg = FakeMessage(id="msg-2")

    count = await scheduler._process_trigger_entries(
        "course-1", [(msg, "sg-1", "root-1")]
    )

    assert count == 1
    trigger = triggers[0][0].message_trigger
    assert trigger.is_follow_up is True
    assert trigger.root_message_id == "root-1"


async def test_process_trigger_entries_isolates_failures():
    """A failure outside _process_message (here: subscribe) must not abort
    the remaining entries of the batch."""
    ws = ExplodingSubscribeWS()
    scheduler, triggers = make_scheduler(ws=ws)

    bad = FakeMessage(id="msg-bad")
    good = FakeMessage(id="msg-good")

    count = await scheduler._process_trigger_entries(
        "course-1", [(bad, "sg-bad", None), (good, "sg-good", None)]
    )

    assert count == 1
    assert [entry[2] for entry in triggers] == ["submission_group:sg-good"]
    assert ws.marked_read == [("submission_group:sg-good", "msg-good")]
