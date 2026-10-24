"""Course conversations use the same authorized mention/reply path as exercises."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from computor_agent.tutor.agent import TutorAgent
from computor_agent.tutor.config import TutorConfig, TriggerConfig
from computor_agent.tutor.websocket.scheduler import WebSocketScheduler
from tests.test_websocket_scheduler import FakeWS


def message(id="question", author="student", parent=None, sg=None, content="Why use Python?"):
    return SimpleNamespace(
        id=id,
        author_id=author,
        parent_id=parent,
        submission_group_id=sg,
        content=content,
        title="Question",
        is_deleted=False,
    )


def scheduler_for(messages, mentioned):
    client = SimpleNamespace(
        messages=SimpleNamespace(
            list=AsyncMock(side_effect=[mentioned, messages]),
            mark_read=AsyncMock(),
            get_thread=AsyncMock(
                return_value=SimpleNamespace(root_message_id="question", messages=messages)
            ),
        )
    )
    callback = AsyncMock()
    scheduler = WebSocketScheduler(
        client=client,
        ws=FakeWS(),
        trigger_config=TriggerConfig(agent_user_id="lena"),
        on_message_trigger=callback,
        cooldown_seconds=0,
    )
    return scheduler, callback


@pytest.mark.parametrize(
    "sg,channel", [(None, "course:course"), ("exercise", "submission_group:exercise")]
)
async def test_mentions_dispatch_and_deduplicate(sg, channel):
    question = message(sg=sg)
    scheduler, callback = scheduler_for([question], [question])
    entries = await scheduler._classify_unread_for_course("course")
    assert len(entries) == 1
    assert await scheduler._process_trigger_entries("course", entries) == 1
    assert await scheduler._process_trigger_entries("course", entries) == 0
    trigger = callback.await_args.args[0].message_trigger
    assert trigger.submission_group_id == sg
    assert callback.await_args.args[2] == channel
    assert scheduler._ws.marked_read == [(channel, "question")]


@pytest.mark.parametrize("sg", [None, "exercise"])
async def test_course_follow_up_but_no_explicit_human_recipient_or_self_loop(sg):
    reply = message("reply", parent="answer", sg=sg)
    human = message("human", parent="answer", sg=sg, content="@[Human](human-id) please check")
    own = message("answer", author="lena", parent="question", sg=sg)
    scheduler, callback = scheduler_for([reply, human, own], [])
    entries = await scheduler._classify_unread_for_course("course")
    assert [entry[0].id for entry in entries] == ["reply"]
    assert await scheduler._process_trigger_entries("course", entries) == 1
    assert callback.await_args.args[0].root_message_id == "question"


async def test_course_agent_replies_to_authorized_parent_without_submission_access():
    thread = SimpleNamespace(
        root_message_id="question",
        messages=[
            SimpleNamespace(
                id="question",
                title="Original",
                content="Earlier question about arrays",
                author_id="student",
                author=None,
            )
        ],
    )
    client = SimpleNamespace(
        messages=SimpleNamespace(
            get_thread=AsyncMock(return_value=thread),
            create=AsyncMock(return_value=SimpleNamespace(id="answer")),
        )
    )
    client.submission_groups = SimpleNamespace(get=AsyncMock())
    llm = SimpleNamespace(complete=AsyncMock(return_value="Python can help with data analysis."))
    config = TutorConfig.from_dict(
        {
            "security": {"enabled": False},
            "notes": {"enabled": False},
            "figure_review": {"enabled": False},
        }
    )
    agent = TutorAgent(config=config, llm=llm, client=client)
    result = await agent.process_message(
        None,
        {
            "id": "reply",
            "author_id": "student",
            "content": "Why use Python?",
            "thread_root_id": "question",
            "course_id": "course",
        },
    )
    assert result.success, result.error
    assert result.message_sent
    client.submission_groups.get.assert_not_awaited()
    assert client.messages.create.await_args.kwargs["data"]["parent_id"] == "reply"
    assert "submission_group_id" not in client.messages.create.await_args.kwargs["data"]
    client.messages.get_thread.assert_awaited_once_with("question")
    assert "Earlier question about arrays" in llm.complete.await_args.kwargs["system_prompt"]


async def test_member_conversation_uses_private_member_channel_for_typing_and_read():
    from computor_types.messages import MessageList

    # The frozen SDK's real list DTO must retain the private target.
    question = MessageList.model_validate(
        {
            "id": "question",
            "content": "How should I study?",
            "level": 0,
            "author_id": "student",
            "course_member_id": "own-membership",
        }
    )
    scheduler, callback = scheduler_for([question], [question])
    entries = await scheduler._classify_unread_for_course("course")
    assert await scheduler._process_trigger_entries("course", entries) == 1
    channel = "course_member:own-membership"
    assert callback.await_args.args[2] == channel
    assert scheduler._ws.marked_read == [(channel, "question")]
    assert scheduler._ws.typing_events == [("start", channel), ("stop", channel)]


async def test_direct_course_replies_share_real_root_lock_and_keep_direct_semantics():
    import asyncio

    first = message("first", parent="earlier")
    second = message("second", parent="first")
    scheduler, callback = scheduler_for([first, second], [first, second])
    entries = await scheduler._classify_unread_for_course("course")
    entered, release = asyncio.Event(), asyncio.Event()

    async def hold(*args):
        entered.set()
        await release.wait()

    callback.side_effect = hold
    running = asyncio.create_task(scheduler._process_trigger_entries("course", [entries[0]]))
    await entered.wait()
    try:
        assert (
            await asyncio.wait_for(
                scheduler._process_trigger_entries("course", [entries[1]]), timeout=1
            )
            == 0
        )
    finally:
        release.set()
        await running
    assert await scheduler._process_trigger_entries("course", [entries[1]]) == 1
    assert callback.await_count == 2
    for call in callback.await_args_list:
        result = call.args[0]
        assert result.root_message_id == "question"
        assert not result.message_trigger.is_follow_up
