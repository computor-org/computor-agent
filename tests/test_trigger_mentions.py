"""Tests for @mention-based tutor activation in TriggerChecker.

The agent activates on messages that @mention it (``mentions_me`` resolved
server-side) and on follow-up replies in threads it already participated in
(matched by authorship). These tests exercise that decision logic with a
mock messages API — the mention *matching* itself lives in the backend, so
here we only assert how the agent reacts to the API's answers.
"""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

from computor_agent.tutor.config import TriggerConfig
from computor_agent.tutor.trigger import TriggerChecker

AGENT_ID = "agent-1"
SG = "sg-1"
COURSE = "course-1"


def _msg(id, author_id, *, parent_id=None, content="hi", title="", created_at=None):
    """A lightweight stand-in for a MessageList row (attribute access only)."""
    return SimpleNamespace(
        id=id,
        author_id=author_id,
        parent_id=parent_id,
        content=content,
        title=title,
        created_at=created_at or datetime(2026, 1, 1),
        author_course_member=None,
    )


def _thread(root_id, messages):
    """A thread payload as MessageThread.model_validate expects it."""
    return {
        "root_message_id": root_id,
        "messages": [
            {"id": m.id, "author_id": m.author_id, "content": "x", "level": 0}
            for m in messages
        ],
    }


def _checker(*, mentions=None, unread=None, thread=None, config=None):
    """Build a TriggerChecker whose messages API returns canned results.

    ``messages.list`` distinguishes the two query shapes the checker issues:
    the new-conversation query passes ``mentions_me=True``; the follow-up
    query does not.
    """
    messages = AsyncMock()

    async def list_side_effect(**kwargs):
        if kwargs.get("mentions_me"):
            return list(mentions or [])
        return list(unread or [])

    messages.list.side_effect = list_side_effect
    messages.thread.return_value = thread or _thread("root", [])

    course_members = AsyncMock()
    course_members.list.return_value = []

    cfg = config or TriggerConfig(agent_user_id=AGENT_ID)
    return TriggerChecker(messages, course_members, cfg)


class TestMentionTrigger:
    async def test_mention_starts_new_conversation(self):
        student = _msg("m-1", "student-1")
        checker = _checker(mentions=[student])

        result = await checker.check_message_trigger(SG, COURSE)

        assert result.should_respond is True
        assert result.message_trigger is not None
        assert result.message_trigger.message_id == "m-1"
        assert result.message_trigger.is_follow_up is False
        assert result.root_message_id == "m-1"
        assert "mention" in result.reason.lower()

    async def test_agents_own_mention_is_excluded(self):
        # A message "mentioning" the agent but authored by the agent itself
        # must not trigger a response (no unread replies either).
        own = _msg("m-own", AGENT_ID)
        checker = _checker(mentions=[own], unread=[])

        result = await checker.check_message_trigger(SG, COURSE)

        assert result.should_respond is False

    async def test_no_mention_no_trigger(self):
        checker = _checker(mentions=[], unread=[])

        result = await checker.check_message_trigger(SG, COURSE)

        assert result.should_respond is False

    async def test_oldest_mention_is_picked(self):
        newer = _msg("m-new", "student-1", created_at=datetime(2026, 1, 2))
        older = _msg("m-old", "student-2", created_at=datetime(2026, 1, 1))
        checker = _checker(mentions=[newer, older])

        result = await checker.check_message_trigger(SG, COURSE)

        assert result.should_respond is True
        assert result.message_trigger.message_id == "m-old"

    async def test_disabled_config_never_triggers(self):
        student = _msg("m-1", "student-1")
        checker = _checker(
            mentions=[student],
            config=TriggerConfig(enabled=False, agent_user_id=AGENT_ID),
        )

        result = await checker.check_message_trigger(SG, COURSE)

        assert result.should_respond is False
        assert "disabled" in result.reason.lower()


class TestFollowUpTrigger:
    async def test_reply_in_agent_thread_triggers(self):
        # No fresh @mention, but an unread reply in a thread the agent already
        # posted in -> follow-up trigger.
        reply = _msg("m-reply", "student-1", parent_id="root")
        thread = _thread("root", [_msg("m-root", "student-1"), _msg("m-a", AGENT_ID)])
        checker = _checker(mentions=[], unread=[reply], thread=thread)

        result = await checker.check_message_trigger(SG, COURSE)

        assert result.should_respond is True
        assert result.message_trigger.is_follow_up is True
        assert result.root_message_id == "root"

    async def test_reply_in_non_agent_thread_does_not_trigger(self):
        # A reply, but the agent never posted in this thread -> no trigger.
        reply = _msg("m-reply", "student-1", parent_id="root")
        thread = _thread("root", [_msg("m-root", "student-1"), _msg("m-b", "tutor-9")])
        checker = _checker(mentions=[], unread=[reply], thread=thread)

        result = await checker.check_message_trigger(SG, COURSE)

        assert result.should_respond is False

    async def test_agents_own_reply_is_not_a_follow_up(self):
        # An unread reply authored by the agent must not trigger the agent.
        reply = _msg("m-reply", AGENT_ID, parent_id="root")
        thread = _thread("root", [_msg("m-a", AGENT_ID)])
        checker = _checker(mentions=[], unread=[reply], thread=thread)

        result = await checker.check_message_trigger(SG, COURSE)

        assert result.should_respond is False
