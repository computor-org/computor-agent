"""The tutor must know WHO it is talking to and WHO said what.

The backend fetches display names for every message author and for every
member of the submission group, but none of it reached the prompt: history
lines were all labeled "[Student]" — including the agent's own replies,
because ``is_from_student`` was hardcoded True in both fetch paths — and the
system prompt had no student section at all. The model could therefore
neither address the student by name nor tell group members apart, and read
its own previous answers as things the student had said.
"""

from types import SimpleNamespace

from computor_agent.tutor.agent import TutorAgent
from computor_agent.tutor.config import ContextConfig, TriggerConfig
from computor_agent.tutor.context import (
    ConversationContext,
    MessageInfo,
    StudentInfo,
    TriggerType,
)
from computor_agent.tutor.context_builder import ContextBuilder
from computor_agent.tutor.prompts.templates import TUTOR_SYSTEM_PROMPT

AGENT_ID = "agent-user-1"


def _msg(i: int, author_id: str, name: str | None):
    if name:
        given, _, family = name.partition(" ")
        author = SimpleNamespace(given_name=given, family_name=family or None)
    else:
        author = None
    return SimpleNamespace(
        id=f"m-{i}", title="", content=f"turn-{i}", author_id=author_id, author=author
    )


class _MessagesEndpoint:
    def __init__(self, messages):
        self._messages = messages

    async def list(self, **kwargs):
        return self._messages

    async def get_thread(self, root_id):
        return SimpleNamespace(messages=self._messages)


def _builder(messages, agent_user_id=AGENT_ID) -> ContextBuilder:
    client = SimpleNamespace(messages=_MessagesEndpoint(messages))
    return ContextBuilder(
        client,
        ContextConfig(),
        trigger_config=TriggerConfig(agent_user_id=agent_user_id),
    )


class TestHistoryAttribution:
    async def test_agent_messages_are_labeled_tutor(self):
        messages = [_msg(0, "student-1", "Max Mandlez"), _msg(1, AGENT_ID, "Luna Tutor")]

        result = await _builder(messages)._get_previous_messages("sg-1")

        assert [m.is_from_student for m in result] == [True, False]

    async def test_thread_fetch_attributes_the_same_way(self):
        messages = [_msg(0, "student-1", "Max Mandlez"), _msg(1, AGENT_ID, "Luna Tutor")]

        result = await _builder(messages)._get_thread_messages("m-0")

        assert [m.is_from_student for m in result] == [True, False]

    async def test_unresolved_agent_id_keeps_everyone_a_student(self):
        """Before startup resolution nobody can be identified as the agent."""
        messages = [_msg(0, "student-1", "Max"), _msg(1, AGENT_ID, "Luna")]

        result = await _builder(messages, agent_user_id=None)._get_previous_messages("sg-1")

        assert all(m.is_from_student for m in result)

    async def test_author_names_survive_the_fetch(self):
        result = await _builder([_msg(0, "s-1", "Max Mandlez")])._get_previous_messages("sg-1")

        assert result[0].author_name == "Max Mandlez"


class TestTriggerAuthorBackfill:
    async def test_trigger_author_name_is_recovered_from_history(self):
        """The scheduler's trigger dict has no author — the fetched copy does."""
        builder = _builder([_msg(0, "student-1", "Max Mandlez")])

        context = await builder.build_for_message(
            submission_group_id="sg-1",
            message={"id": "m-0", "content": "turn-0", "author_id": "student-1"},
        )

        assert context.trigger_message.author_name == "Max Mandlez"


class TestFormattedLabels:
    def _context(self, messages) -> ConversationContext:
        return ConversationContext(
            trigger_type=TriggerType.MESSAGE,
            submission_group_id="sg-1",
            previous_messages=messages,
        )

    def test_named_speakers_show_name_and_role(self):
        formatted = self._context(
            [
                MessageInfo(id="1", title="", content="hi", author_id="s1",
                            author_name="Max Mandlez", is_from_student=True),
                MessageInfo(id="2", title="", content="hello", author_id=AGENT_ID,
                            author_name="Luna", is_from_student=False),
            ]
        ).get_formatted_previous_messages()

        assert "[Max Mandlez (Student)]: hi" in formatted
        assert "[Luna (Tutor)]: hello" in formatted

    def test_unnamed_speakers_fall_back_to_bare_roles(self):
        formatted = self._context(
            [
                MessageInfo(id="1", title="", content="hi", author_id="s1"),
                MessageInfo(id="2", title="", content="hello", author_id=AGENT_ID,
                            is_from_student=False),
            ]
        ).get_formatted_previous_messages()

        assert "[Student]: hi" in formatted
        assert "[Tutor]: hello" in formatted


class TestStudentSection:
    def _section(self, names, trigger_author=None) -> str:
        context = ConversationContext(
            trigger_type=TriggerType.MESSAGE,
            submission_group_id="sg-1",
            student=StudentInfo(names=names),
            trigger_message=MessageInfo(
                id="m-0", title="", content="hi", author_id="s1",
                author_name=trigger_author,
            ),
        )
        # The formatter reads only the context; no agent state is involved.
        return TutorAgent._format_student_section(None, context)

    def test_solo_student_is_named_once(self):
        assert self._section(["Max Mandlez"], "Max Mandlez") == "Student: Max Mandlez"

    def test_group_members_are_all_named(self):
        section = self._section(["Max Mandlez", "Erika Muster"])

        assert "Max Mandlez" in section and "Erika Muster" in section

    def test_group_thread_names_the_current_author(self):
        section = self._section(["Max Mandlez", "Erika Muster"], "Erika Muster")

        assert "The current message was written by: Erika Muster" in section

    def test_no_names_means_an_empty_section(self):
        assert self._section([]) == ""

    def test_the_template_and_the_agent_carry_the_section(self):
        """Guard against the placeholder or the format kwarg drifting out."""
        import inspect

        assert "{student_section}" in TUTOR_SYSTEM_PROMPT
        source = inspect.getsource(TutorAgent._build_system_prompt)
        assert "student_section=" in source
