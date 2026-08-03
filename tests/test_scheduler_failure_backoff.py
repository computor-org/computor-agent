"""A message that fails to process must not be retried in a tight loop.

The failure path skips both the read-marking and the last-processed bookkeeping,
so a failed message stayed unread and untracked: every `message:new` event and
every periodic catch-up scan re-selected it. With the LLM unreachable that
hammered the backend and the provider continuously, and a message that always
crashes the pipeline retried forever.
"""

from datetime import datetime, timedelta

from computor_agent.tutor.websocket.scheduler import (
    MAX_MESSAGE_ATTEMPTS,
    WebSocketScheduler,
)


class FakeWS:
    is_connected = True

    def __init__(self):
        self.subscribed: list[str] = []
        self.marked_read: list[tuple[str, str]] = []

    async def subscribe(self, channels):
        self.subscribed.extend(channels)

    async def mark_read(self, channel, message_id):
        self.marked_read.append((channel, message_id))

    async def send_typing_start(self, channel):
        pass

    async def send_typing_stop(self, channel):
        pass


class FakeMessage:
    def __init__(self, id, content="hello @tutor", title="Question", author_id="student-1"):
        self.id = id
        self.content = content
        self.title = title
        self.author_id = author_id


def make_scheduler(fail: bool):
    """Scheduler whose trigger callback either works or always raises."""
    calls: list[str] = []

    async def on_trigger(result, course_content, channel):
        calls.append(result.message_trigger.message_id)
        if fail:
            raise RuntimeError("LLM unreachable")

    scheduler = WebSocketScheduler(
        client=object(),
        ws=FakeWS(),
        on_message_trigger=on_trigger,
        cooldown_seconds=0,
    )
    return scheduler, calls


async def _process(scheduler, message_id="msg-1", group="sg-1"):
    return await scheduler._process_trigger_entries(
        "course-1", [(FakeMessage(id=message_id), group, None)]
    )


async def test_a_failed_message_is_not_retried_immediately():
    """The regression: the next scan used to pick the same message straight up."""
    scheduler, calls = make_scheduler(fail=True)

    await _process(scheduler)
    assert calls == ["msg-1"]

    # Second scan, moments later: must be backed off, not re-attempted.
    await _process(scheduler)
    assert calls == ["msg-1"], "message was retried with no delay"


async def test_the_retry_becomes_due_after_the_backoff():
    scheduler, calls = make_scheduler(fail=True)
    await _process(scheduler)

    # Pretend the delay has elapsed.
    scheduler._failures["msg-1"].retry_after = datetime.now() - timedelta(seconds=1)
    await _process(scheduler)

    assert calls == ["msg-1", "msg-1"]


async def test_the_delay_grows_with_each_failure():
    scheduler, _ = make_scheduler(fail=True)
    delays = []

    for _ in range(3):
        await _process(scheduler)
        failure = scheduler._failures["msg-1"]
        delays.append((failure.retry_after - datetime.now()).total_seconds())
        failure.retry_after = datetime.now() - timedelta(seconds=1)

    assert delays[1] > delays[0]
    assert delays[2] > delays[1]


async def test_a_message_is_parked_after_repeated_failures():
    scheduler, calls = make_scheduler(fail=True)

    # Run past the attempt limit, clearing the delay each round.
    for _ in range(MAX_MESSAGE_ATTEMPTS + 3):
        failure = scheduler._failures.get("msg-1")
        if failure and failure.retry_after:
            failure.retry_after = datetime.now() - timedelta(seconds=1)
        await _process(scheduler)

    assert len(calls) == MAX_MESSAGE_ATTEMPTS
    assert scheduler._failures["msg-1"].parked is True
    assert scheduler.get_stats()["parked_messages"] == 1


async def test_a_parked_message_stays_unread_so_a_restart_can_retry_it():
    """Parking is in-memory: never bury the student's message on the server."""
    scheduler, _ = make_scheduler(fail=True)

    for _ in range(MAX_MESSAGE_ATTEMPTS + 1):
        failure = scheduler._failures.get("msg-1")
        if failure and failure.retry_after:
            failure.retry_after = datetime.now() - timedelta(seconds=1)
        await _process(scheduler)

    assert scheduler._ws.marked_read == []


async def test_success_clears_the_failure_record():
    scheduler, _ = make_scheduler(fail=False)

    # Seed a prior failure, then let the message succeed.
    scheduler._record_failure("msg-1", scheduler._get_or_create_state("sg-1"), RuntimeError("x"))
    scheduler._failures["msg-1"].retry_after = datetime.now() - timedelta(seconds=1)

    count = await _process(scheduler)

    assert count == 1
    assert "msg-1" not in scheduler._failures


async def test_one_failing_message_does_not_back_off_a_different_one():
    scheduler, calls = make_scheduler(fail=True)

    await _process(scheduler, message_id="msg-a", group="sg-a")
    await _process(scheduler, message_id="msg-b", group="sg-b")

    assert calls == ["msg-a", "msg-b"]


async def test_a_full_reset_unparks_everything():
    scheduler, _ = make_scheduler(fail=True)
    await _process(scheduler)
    assert scheduler._failures

    scheduler.reset_state()

    assert scheduler._failures == {}
