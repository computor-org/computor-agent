"""The tutor reads the assignment in the language the learner is reading.

An English reader in a German-configured course asked in English, but the
prompt carried the English description under the German title and named
German as the fallback reply language, because the description was always
fetched as ``index_en.md`` and the fallback came from the static config
(issues#556). The backend now records the learner's reading language with
each message; older backends do not, and then the old behaviour holds.
"""

import io
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from computor_agent.tutor.prompts import loader as loader_module
from computor_agent.tutor.prompts.loader import PromptLoader
from computor_agent.runtime import AgentRuntime, RuntimeOptions
from computor_agent.tutor.agent import TutorAgent
from computor_agent.tutor.config import ContextConfig, TutorConfig
from computor_agent.tutor.context_builder import ContextBuilder
from tests.test_websocket_scheduler import FakeMessage, make_scheduler

DE_TEXT = "Schreibe eine Schleife, die bis zehn zählt."
EN_TEXT = "Write a loop that counts to ten."


@pytest.fixture(autouse=True)
def _reset_global_loader():
    """The loader is a module-level singleton; don't leak it between tests."""
    original = loader_module._prompt_loader
    yield
    loader_module._prompt_loader = original


def _description_zip() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("index_de.md", DE_TEXT)
        zf.writestr("index_en.md", EN_TEXT)
    return buffer.getvalue()


def _client(title_i18n=None):
    content = SimpleNamespace(title="Schleifen", course_id="c-1")
    if title_i18n is not None:
        content.title_i18n = title_i18n
    return SimpleNamespace(
        submission_groups=SimpleNamespace(
            get=AsyncMock(return_value=SimpleNamespace(course_content_id="cc-1"))
        ),
        course_contents=SimpleNamespace(get=AsyncMock(return_value=content)),
        tutors=SimpleNamespace(
            get_course_contents_description=AsyncMock(return_value=_description_zip())
        ),
        messages=SimpleNamespace(list=AsyncMock(return_value=[])),
    )


async def _prompt_for(tmp_path: Path, listed_message, title_i18n=None) -> tuple:
    """Run a listed message through scheduler, runtime callback, builder and prompt."""
    scheduler, triggers = make_scheduler()
    await scheduler._process_trigger_entries("course-1", [(listed_message, "sg-1", None)])
    result, course_content, _channel = triggers[0]

    agent = SimpleNamespace(
        process_message=AsyncMock(return_value=SimpleNamespace(success=True))
    )
    runtime = object.__new__(AgentRuntime)
    runtime.options = RuntimeOptions()
    await runtime._make_trigger_callback(agent)(result, course_content, "submission_group:sg-1")
    message = agent.process_message.await_args.kwargs["message"]

    builder = ContextBuilder(_client(title_i18n), ContextConfig(cache_dir=tmp_path / "cache"))
    context = await builder.build_for_message(submission_group_id="sg-1", message=message)

    loader_module._prompt_loader = PromptLoader(prompts_dir=tmp_path, enable_hot_reload=False)
    tutor = TutorAgent(
        config=TutorConfig(personality={"language": "de"}), llm=object(), client=SimpleNamespace()
    )
    return context, tutor._build_system_prompt(context)


@pytest.mark.parametrize(
    "reading, text, title",
    [("en", EN_TEXT, "Loops"), ("de", DE_TEXT, "Schleifen")],
)
async def test_assignment_and_fallback_follow_the_reading_language(tmp_path, reading, text, title):
    message = FakeMessage(id="msg-1", content="How do I stop my loop?")
    message.reading_language = reading

    context, prompt = await _prompt_for(
        tmp_path, message, title_i18n={"de": "Schleifen", "en": "Loops"}
    )

    assert context.assignment.description == text
    assert context.assignment.title == title
    assert f"fall back to {reading}." in prompt
    assert f"Title: {title}\n{text}" in prompt


async def test_a_backend_without_the_field_keeps_the_old_behaviour(tmp_path):
    context, prompt = await _prompt_for(tmp_path, FakeMessage(id="msg-1"))

    assert context.assignment.description == EN_TEXT
    assert context.assignment.title == "Schleifen"
    assert "fall back to de." in prompt


async def test_untranslated_title_falls_back_to_the_single_title(tmp_path):
    message = FakeMessage(id="msg-1")
    message.reading_language = "en"

    context, _prompt = await _prompt_for(tmp_path, message, title_i18n={"de": "Schleifen"})

    assert context.assignment.title == "Schleifen"
