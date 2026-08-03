"""The tutor must see the END of a conversation, not the beginning.

`previous_messages` is documented and consumed as "most recent last". The
context builder sliced it from the *front*, so on any thread longer than the
configured limit the agent was handed the opening turns and lost everything the
student had just said. On top of that, the agent called the formatter with no
argument, so its default of 3 capped every thread regardless of configuration.
"""

import pytest

from computor_agent.tutor.context import ConversationContext, MessageInfo
from computor_agent.tutor.context_builder import take_recent_messages
from computor_agent.tutor.config import ContextConfig
from computor_agent.tutor.context import TriggerType


def _messages(count: int) -> list[MessageInfo]:
    """Oldest first, newest last - the documented ordering."""
    return [
        MessageInfo(
            id=f"m-{i}",
            title=f"Message {i}",
            content=f"turn-{i}",
            author_id=f"a-{i}",
            is_from_student=i % 2 == 0,
        )
        for i in range(count)
    ]


def _context(messages: list[MessageInfo]) -> ConversationContext:
    return ConversationContext(
        trigger_type=TriggerType.MESSAGE,
        submission_group_id="sg-1",
        previous_messages=messages,
    )


class TestFormattedPreviousMessages:
    def test_keeps_the_most_recent_turns(self):
        formatted = _context(_messages(10)).get_formatted_previous_messages(max_messages=3)

        assert "turn-9" in formatted
        assert "turn-8" in formatted
        assert "turn-7" in formatted
        assert "turn-0" not in formatted

    def test_honours_a_limit_above_the_old_hardcoded_three(self):
        formatted = _context(_messages(10)).get_formatted_previous_messages(max_messages=8)

        assert formatted.count("turn-") == 8
        assert "turn-2" in formatted

    def test_zero_means_none_not_everything(self):
        """`list[-0:]` is the whole list - the guard for this is load-bearing."""
        formatted = _context(_messages(5)).get_formatted_previous_messages(max_messages=0)

        assert formatted == "(No previous messages)"

    def test_shorter_history_than_the_limit_is_fine(self):
        formatted = _context(_messages(2)).get_formatted_previous_messages(max_messages=5)

        assert "turn-0" in formatted and "turn-1" in formatted


class TestBuilderTruncation:
    """The builder's own truncation must also keep the tail."""

    def test_truncation_keeps_the_newest_messages(self):
        kept = take_recent_messages(_messages(10), 4)

        assert [m.content for m in kept] == ["turn-6", "turn-7", "turn-8", "turn-9"]

    def test_zero_keeps_nothing(self):
        assert take_recent_messages(_messages(10), 0) == []

    def test_limit_beyond_the_history_keeps_all_of_it(self):
        assert len(take_recent_messages(_messages(3), 10)) == 3

    def test_the_builder_actually_uses_it(self):
        """Guard against the call site drifting back to a head slice."""
        import inspect
        from computor_agent.tutor import context_builder

        source = inspect.getsource(context_builder.ContextBuilder._build_context)
        assert "take_recent_messages(" in source

    def test_default_config_limit_is_applied_as_a_tail(self):
        limit = ContextConfig().include_previous_messages
        kept = take_recent_messages(_messages(limit + 5), limit)

        assert len(kept) == limit
        assert kept[-1].content == f"turn-{limit + 4}"


class TestAgentPassesTheConfiguredLimit:
    def test_configured_limit_reaches_the_formatter(self):
        """Regression: the agent used to call the formatter with no argument."""
        import inspect
        from computor_agent.tutor import agent as agent_module

        source = inspect.getsource(agent_module.TutorAgent)
        assert "get_formatted_previous_messages(" in source
        assert "include_previous_messages" in source, (
            "the agent must pass the configured limit, not fall back to the "
            "formatter's default of 3"
        )
