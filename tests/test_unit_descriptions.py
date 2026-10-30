"""Unit description drafts for lecturers (computor-org/issues#559)."""

import asyncio
import logging

import pytest

from computor_agent.llm.base import LLMResponse
from computor_agent.tutor import unit_descriptions as drafts
from computor_agent.tutor.config import TutorConfig, UnitDescriptionConfig
from computor_agent.tutor.prompts import loader

TEXT_MARKER = "ASSIGNMENT-TEXT-3c9e1a"
DRAFT_MARKER = "DRAFT-TEXT-8b2f47"

REQUEST = {
    "unit_title": "Week 1",
    "unit_description": None,
    "course_title": "Programming 1",
    "languages": ["de", "en"],
    "instruction": "Mention the quiz",
    "assignments": [
        {"title": "Loops", "content_type": "Exercise", "text": f"Write a for loop {TEXT_MARKER}", "text_language": "en"},
        {"title": "Lists", "content_type": None, "text": "", "text_language": None},
    ],
}


class FakeLLM:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = []

    async def complete(self, prompt, *, system_prompt=None, **kwargs):
        self.calls.append({"prompt": prompt, "system_prompt": system_prompt, **kwargs})
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        if isinstance(answer, float):
            await asyncio.sleep(answer)
            answer = "late"
        if isinstance(answer, LLMResponse):
            return answer
        return LLMResponse(content=answer, model="m", finish_reason="stop")


@pytest.fixture(autouse=True)
def builtin_prompts(tmp_path):
    # An empty prompts directory: the built-in prompt is used.
    loader.get_prompt_loader(prompts_dir=tmp_path, force_reload=True)
    yield
    loader._prompt_loader = None


def writer(llm):
    return drafts.UnitDescriptionWriter(llm, UnitDescriptionConfig())


def test_user_message_carries_the_job_input():
    message = drafts.build_user_message(REQUEST, "de")
    assert "Unit: Week 1" in message and "Course: Programming 1" in message
    assert "Write the description in: German" in message
    assert "Lecturer's extra instruction: Mention the quiz" in message
    assert "### 1. Loops (Exercise)" in message and TEXT_MARKER in message
    assert "### 2. Lists\n\n(no assignment text available)" in message
    assert "Current unit description: none" in message


def test_clean_draft_drops_reasoning_and_fence():
    assert drafts.clean_draft("<think>plan</think>\n```markdown\n# Week 1\nText\n```") == "# Week 1\nText"
    assert drafts.clean_draft(None) == ""


@pytest.mark.asyncio
async def test_one_draft_per_language():
    llm = FakeLLM("Woche 1", "Week 1")
    body = await writer(llm).completion({"lease": "7", "request": REQUEST})
    assert body == {
        "lease": "7",
        "state": "done",
        "drafts": [{"language": "de", "description": "Woche 1"}, {"language": "en", "description": "Week 1"}],
    }
    assert "German" in llm.calls[0]["system_prompt"] and "English" in llm.calls[1]["system_prompt"]
    assert "{language_name}" not in llm.calls[0]["system_prompt"]
    assert llm.calls[0]["max_tokens"] == 2048 and llm.calls[0]["temperature"] == 0.3


@pytest.mark.asyncio
async def test_too_long_is_retried_once_then_fails_without_cutting():
    long_text = "x" * 5000
    llm = FakeLLM(long_text, "short enough")
    assert await writer(llm).write(REQUEST, "en") == "short enough"
    assert "at most 3000 characters" in llm.calls[1]["prompt"]

    body = await writer(FakeLLM(long_text, long_text)).completion({"lease": "1", "request": REQUEST})
    assert body == {"lease": "1", "state": "failed", "error": "too_long"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("answer", "code"),
    [
        (RuntimeError("upstream said: " + TEXT_MARKER), "model_error"),
        (LLMResponse(content="x", model="m", finish_reason="content_filter"), "invalid_output"),
        ("   ", "invalid_output"),
    ],
)
async def test_failures_become_error_codes(answer, code):
    body = await writer(FakeLLM(answer)).completion({"lease": "1", "request": REQUEST})
    assert body == {"lease": "1", "state": "failed", "error": code}


def cut(content):
    return LLMResponse(content=content, model="m", finish_reason="length")


@pytest.mark.asyncio
async def test_budget_spent_on_reasoning_is_retried_with_more_tokens():
    llm = FakeLLM(cut("<think>still planning"), "Week 1")
    assert await writer(llm).write(REQUEST, "en") == "Week 1"
    assert [call["max_tokens"] for call in llm.calls] == [2048, 4096]

    llm = FakeLLM(cut(""), cut("<think>"))
    body = await writer(llm).completion({"lease": "1", "request": REQUEST})
    assert body == {"lease": "1", "state": "failed", "error": "model_error"}


@pytest.mark.asyncio
async def test_cut_off_long_answer_is_asked_for_shorter():
    llm = FakeLLM(cut("x" * 5000), "short enough")
    assert await writer(llm).write(REQUEST, "en") == "short enough"
    assert "at most 3000 characters" in llm.calls[1]["prompt"]

    llm = FakeLLM(cut("x" * 5000), cut("x" * 5000))
    body = await writer(llm).completion({"lease": "1", "request": REQUEST})
    assert body == {"lease": "1", "state": "failed", "error": "too_long"}


@pytest.mark.asyncio
async def test_job_ends_before_the_lease():
    config = UnitDescriptionConfig().model_copy(update={"job_timeout_seconds": 0.05})
    slow = drafts.UnitDescriptionWriter(FakeLLM("Woche 1", 1.0), config)
    body = await slow.completion({"lease": "1", "request": REQUEST})
    assert body == {"lease": "1", "state": "failed", "error": "model_error"}
    assert UnitDescriptionConfig().job_timeout_seconds < 600


@pytest.mark.asyncio
async def test_operator_prompt_override_with_braces(tmp_path):
    (tmp_path / "unit_description").mkdir()
    (tmp_path / "unit_description" / "unit_description.md").write_text(
        'Describe the unit in {language_name}. Example: {"title": "x"}'
    )
    loader.get_prompt_loader(prompts_dir=tmp_path, force_reload=True)
    llm = FakeLLM("Week 1")
    await writer(llm).write(REQUEST, "en")
    assert llm.calls[0]["system_prompt"] == 'Describe the unit in English. Example: {"title": "x"}'


def http_error(status):
    error = RuntimeError(f"HTTP {status}")
    error.status_code = status
    return error


class FakeClient:
    def __init__(self, claims, complete_errors=()):
        self.claims = list(claims)
        self.posts = []
        # Raised by the completion calls in turn; then they succeed.
        self.complete_errors = list(complete_errors)

    async def post(self, path, *, json_data=None, **_kwargs):
        self.posts.append((path, json_data))
        if path == drafts.CLAIM_PATH:
            claim = self.claims.pop(0)
            if isinstance(claim, Exception):
                raise claim
            return claim
        if self.complete_errors:
            raise self.complete_errors.pop(0)
        return {"state": "finished"}


def worker(client, llm):
    return drafts.UnitDescriptionWorker(client, llm, UnitDescriptionConfig(poll_interval_seconds=2))


@pytest.mark.asyncio
async def test_worker_claims_writes_and_completes(caplog):
    caplog.set_level(logging.DEBUG)
    job_id = "8a5c2f8e-3b9e-4b8e-9a62-0d6a4f4d2c11"
    client = FakeClient([
        {"state": "claimed", "id": job_id, "lease": "3", "request": REQUEST},
        {"state": "idle"},
    ])
    w = worker(client, FakeLLM(f"Woche 1 {DRAFT_MARKER}", "Week 1"))
    assert await w.poll_once() == 0.0
    path, body = client.posts[1]
    assert path == f"/course-contents/description-drafts/worker/complete/{job_id}"
    assert body["state"] == "done" and body["lease"] == "3"
    assert await w.poll_once() == 2
    # Assignment text and drafts never reach the logs.
    assert TEXT_MARKER not in caplog.text and DRAFT_MARKER not in caplog.text


JOB_ID = "8a5c2f8e-3b9e-4b8e-9a62-0d6a4f4d2c11"


def claimed(job_id=JOB_ID):
    return {"state": "claimed", "id": job_id, "lease": "3", "request": REQUEST}


@pytest.mark.asyncio
async def test_cancelled_job_is_dropped_without_backoff(caplog):
    caplog.set_level(logging.INFO)
    client = FakeClient([claimed()], complete_errors=[http_error(409)])
    assert await worker(client, FakeLLM("Woche 1", "Week 1")).poll_once() == 0.0
    assert len(client.posts) == 2
    assert "dropped" in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [400, 422])
async def test_refused_drafts_fail_the_job(status):
    client = FakeClient([claimed()], complete_errors=[http_error(status)])
    assert await worker(client, FakeLLM("Woche 1", "Week 1")).poll_once() == 0.0
    path, body = client.posts[2]
    assert path == f"/course-contents/description-drafts/worker/complete/{JOB_ID}"
    assert body == {"lease": "3", "state": "failed", "error": "invalid_output"}


@pytest.mark.asyncio
async def test_refused_failure_is_not_sent_again():
    client = FakeClient([claimed()], complete_errors=[http_error(422)])
    w = worker(client, FakeLLM(RuntimeError("down")))
    assert await w.poll_once() == drafts.ERROR_BACKOFF_SECONDS
    assert len(client.posts) == 2


@pytest.mark.asyncio
async def test_refused_drafts_then_failing_fails_too():
    client = FakeClient([claimed()], complete_errors=[http_error(422), http_error(503)])
    w = worker(client, FakeLLM("Woche 1", "Week 1"))
    assert await w.poll_once() == drafts.ERROR_BACKOFF_SECONDS
    assert len(client.posts) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("job_id", ["../../users/me", None, "", "8a5c2f8e"])
async def test_claim_with_a_bad_job_id_is_skipped(job_id):
    llm = FakeLLM()
    client = FakeClient([claimed(job_id)])
    assert await worker(client, llm).poll_once() == drafts.ERROR_BACKOFF_SECONDS
    assert len(client.posts) == 1 and llm.calls == []


@pytest.mark.asyncio
async def test_worker_backs_off_on_old_backend(caplog):
    caplog.set_level(logging.INFO)
    error = http_error(404)
    client = FakeClient([error, error])
    w = worker(client, FakeLLM())
    assert await w.poll_once() == drafts.UNSUPPORTED_BACKOFF_SECONDS
    assert await w.poll_once() == drafts.UNSUPPORTED_BACKOFF_SECONDS
    assert caplog.text.count("unavailable on this backend") == 1


@pytest.mark.asyncio
async def test_worker_stops_on_event():
    client = FakeClient([{"state": "idle"}] * 10)
    w = worker(client, FakeLLM())
    stop = asyncio.Event()
    task = asyncio.create_task(w.run(stop))
    await asyncio.sleep(0.05)
    stop.set()
    await asyncio.wait_for(task, timeout=1)


def test_config_section_defaults_on():
    assert TutorConfig().unit_descriptions.enabled is True
    assert TutorConfig.from_dict({"unit_descriptions": {"enabled": False}}).unit_descriptions.enabled is False
