"""Tutor replies and prompts must never reach the console or the -l log file.

Regression for computor-org/issues#501: the tutor agent logged the full AI reply
at INFO. These tests run the real agent -> adapter -> OpenAI provider path under
the CLI's own `setup_logging` and check both sinks (console and log file).
"""

import io
import logging
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from rich.console import Console

from computor_agent.cli import main as cli_main
from computor_agent.llm.config import LLMConfig
from computor_agent.llm.content_logging import set_log_llm_content
from computor_agent.llm.openai_provider import OpenAIProvider
from computor_agent.tutor.agent import TutorAgent
from computor_agent.tutor.client_adapter import TutorLLMAdapter
from computor_agent.tutor.config import TutorConfig
from computor_agent.tutor.context import ConversationContext, MessageInfo, TriggerType
from computor_agent.tutor.security.types import SecurityCheckResult

REPLY_MARKER = "REPLY-MARKER-7f3a9c"
STUDENT_MARKER = "STUDENT-MARKER-51d2e8"
FALLBACK_TEXT = "wasn't able to generate a response"


class FakeMessages:
    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []

    async def create(self, data: dict[str, Any]) -> SimpleNamespace:
        self.created.append(data)
        return SimpleNamespace(id="created-msg-1")

    async def reads(self, id: str) -> None:  # noqa: A002
        return None


def make_agent(reply: str) -> tuple[TutorAgent, FakeMessages]:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"choices": [{"message": {"content": reply}}], "model": "m"}
        )

    provider = OpenAIProvider(LLMConfig(base_url="http://llm.invalid/v1", model="m"))
    provider._client = httpx.AsyncClient(
        base_url="http://llm.invalid/v1", transport=httpx.MockTransport(handler)
    )

    messages = FakeMessages()
    agent = TutorAgent.__new__(TutorAgent)
    agent.config = TutorConfig()
    agent.llm = TutorLLMAdapter(provider)
    agent.client = SimpleNamespace(messages=messages)
    agent.figure_reviewer = None

    async def build_for_message(**kwargs: Any) -> ConversationContext:
        return ConversationContext(
            trigger_type=TriggerType.MESSAGE,
            submission_group_id="sg-1",
            trigger_message=MessageInfo(
                id="student-msg-1",
                title="Question",
                content=kwargs["message"]["content"],
                author_id="student-1",
            ),
        )

    async def noop(*args: Any, **kwargs: Any) -> None:
        return None

    async def check(context: Any) -> SecurityCheckResult:
        return SecurityCheckResult(is_safe=True)

    agent.context_builder = SimpleNamespace(
        build_for_message=build_for_message, ensure_reference_comparison=noop
    )
    agent.security_gate = SimpleNamespace(check=check)
    agent._ensure_code_context = noop
    agent._maybe_review_figures = noop
    return agent, messages


@pytest.fixture
def sinks(tmp_path, monkeypatch):
    """Install the CLI's real logging setup; return (console buffer, log file)."""
    buffer = io.StringIO()
    monkeypatch.setattr(cli_main, "console", Console(file=buffer, width=200))
    root = logging.getLogger()
    saved = (root.handlers[:], root.level)
    log_file = tmp_path / "agent.log"
    yield buffer, log_file
    for handler in root.handlers[:]:
        handler.close()
    root.handlers[:] = saved[0]
    root.setLevel(saved[1])
    set_log_llm_content(False)


def install_cli_logging(verbose: bool, log_file) -> None:
    # basicConfig is a no-op while pytest's capture handlers sit on the root logger.
    logging.getLogger().handlers.clear()
    cli_main.setup_logging(verbose, log_file=str(log_file))


def run_all_output(buffer: io.StringIO, log_file) -> str:
    for handler in logging.getLogger().handlers:
        handler.flush()
    return buffer.getvalue() + log_file.read_text(encoding="utf-8")


@pytest.mark.parametrize("verbose", [False, True], ids=["info", "verbose"])
@pytest.mark.parametrize("path", ["normal", "fallback"])
async def test_content_never_logged(sinks, verbose, path):
    buffer, log_file = sinks
    install_cli_logging(verbose, log_file)
    agent, messages = make_agent(REPLY_MARKER if path == "normal" else "")
    message = {"id": "student-msg-1", "content": STUDENT_MARKER}

    result = await agent.process_message("sg-1", message, reply_to_message_id="student-msg-1")

    assert result.success and result.message_sent
    sent = messages.created[0]
    assert (REPLY_MARKER in sent["content"]) == (path == "normal")
    assert (FALLBACK_TEXT in sent["content"]) == (path == "fallback")

    output = run_all_output(buffer, log_file)
    assert "Creating" in output  # the metadata line was logged, so sinks work
    assert f"content_length={len(sent['content'])}" in output
    assert "created-msg-1" in output
    for secret in (REPLY_MARKER, STUDENT_MARKER, FALLBACK_TEXT):
        assert secret not in output


async def test_llm_dump_requires_explicit_opt_in(sinks):
    buffer, log_file = sinks
    install_cli_logging(True, log_file)
    set_log_llm_content(True)
    agent, _ = make_agent(REPLY_MARKER)

    await agent.process_message(
        "sg-1", {"id": "m1", "content": STUDENT_MARKER}, reply_to_message_id="m1"
    )

    output = run_all_output(buffer, log_file)
    assert REPLY_MARKER in output  # the opt-in dump works, so the tests above bite
    assert STUDENT_MARKER in output


@pytest.mark.parametrize(
    "args, env, expected",
    [
        ([], {}, False),
        (["-v"], {}, False),
        (["-v"], {"COMPUTOR_LOG_LLM_CONTENT": "0"}, False),
        ([], {"COMPUTOR_LOG_LLM_CONTENT": "false"}, False),
        ([], {"COMPUTOR_LOG_LLM_CONTENT": "1"}, True),
        (["--log-llm-content"], {}, True),
    ],
)
def test_messaging_cli_opt_in(monkeypatch, args, env, expected):
    """Only --log-llm-content / a truthy env var enables dumps; -v never does."""
    from click.testing import CliRunner

    from computor_agent.llm import content_logging

    seen: list[bool] = []

    class StopCliError(Exception):
        pass

    def spy(enabled: bool) -> None:
        seen.append(enabled)
        raise StopCliError  # do not start the agent

    monkeypatch.setattr(content_logging, "set_log_llm_content", spy)
    monkeypatch.setattr(cli_main, "setup_logging", lambda *a, **k: None)
    monkeypatch.delenv("COMPUTOR_LOG_LLM_CONTENT", raising=False)

    CliRunner().invoke(cli_main.cli, ["tutor", "messaging", *args], env=env)

    assert seen == [expected]
