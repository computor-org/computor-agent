"""Synthetic network boundary tests for the outbound-only Luna worker."""

import json

import httpx
import pytest

from computor_agent.public_luna_worker import _model_body, _validate_config, process_one

REQUEST = {
    "course_content_id": "00000000-0000-0000-0000-000000000001",
    "assignment": "Explain a loop",
    "question": "Why is my answer empty?",
    "submitted_text": "for x in []: print(x)",
}


def test_only_explicit_bounded_text_reaches_model():
    body = _model_body(REQUEST)
    assert body["model"] == "luna-public"
    assert body["max_tokens"] == 1024
    assert len(body["messages"]) == 2
    assert "Why is my answer empty?" in body["messages"][1]["content"]
    with pytest.raises(ValueError):
        _model_body({**REQUEST, "reference_solution": "private"})
    with pytest.raises(ValueError):
        _model_body({**REQUEST, "submitted_text": "x" * 16001})


def test_worker_requires_https_backend_and_distinct_secrets():
    _validate_config("https://computor.example", "http://10.77.0.20:8080", "a" * 32, "b" * 32)
    with pytest.raises(ValueError):
        _validate_config("http://computor.example", "http://10.77.0.20:8080", "a" * 32, "b" * 32)
    with pytest.raises(ValueError):
        _validate_config("https://computor.example", "http://10.77.0.20:8080", "short", "b" * 32)


@pytest.mark.asyncio
async def test_success_sends_one_answer_without_general_api_token():
    seen = []

    def model_handler(request):
        seen.append(("model", request))
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "Try an input item."}}]}
        )

    def backend_handler(request):
        seen.append(("backend", request))
        return httpx.Response(200, json={"state": "finished"})

    async with (
        httpx.AsyncClient(transport=httpx.MockTransport(backend_handler)) as backend,
        httpx.AsyncClient(transport=httpx.MockTransport(model_handler)) as model,
    ):
        await process_one(
            backend,
            model,
            "https://computor.example",
            "http://10.77.0.20:8080",
            "a" * 32,
            "b" * 32,
            {
                "id": "00000000-0000-0000-0000-000000000002",
                "lease": "7",
                "request": REQUEST,
            },
        )
    assert [kind for kind, _ in seen] == ["model", "backend"]
    assert seen[0][1].headers["Authorization"] == "Bearer " + "b" * 32
    assert seen[1][1].headers.get("X-API-Token") is None
    result = json.loads(seen[1][1].content)
    assert result == {"lease": "7", "state": "done", "answer": "Try an input item."}


@pytest.mark.asyncio
async def test_bad_claim_never_reaches_model_and_reports_generic_failure():
    seen = []

    def model_handler(request):
        pytest.fail("Malformed claim reached model")

    def backend_handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"state": "finished"})

    async with (
        httpx.AsyncClient(transport=httpx.MockTransport(backend_handler)) as backend,
        httpx.AsyncClient(transport=httpx.MockTransport(model_handler)) as model,
    ):
        await process_one(
            backend,
            model,
            "https://computor.example",
            "http://10.77.0.20:8080",
            "a" * 32,
            "b" * 32,
            {
                "id": "00000000-0000-0000-0000-000000000002",
                "lease": "7",
                "request": {**REQUEST, "hidden_tests": "private"},
            },
        )
    assert seen == [{"lease": "7", "state": "failed", "answer": ""}]


@pytest.mark.asyncio
async def test_upstream_error_content_is_not_logged_or_returned(caplog):
    secret = "sentinel private source"
    results = []

    def model_handler(_request):
        return httpx.Response(500, text=secret)

    def backend_handler(request):
        results.append(json.loads(request.content))
        return httpx.Response(200, json={"state": "finished"})

    async with (
        httpx.AsyncClient(transport=httpx.MockTransport(backend_handler)) as backend,
        httpx.AsyncClient(transport=httpx.MockTransport(model_handler)) as model,
    ):
        await process_one(
            backend,
            model,
            "https://computor.example",
            "http://10.77.0.20:8080",
            "a" * 32,
            "b" * 32,
            {"id": "00000000-0000-0000-0000-000000000002", "lease": "7", "request": REQUEST},
        )
    assert results == [{"lease": "7", "state": "failed", "answer": ""}]
    assert secret not in caplog.text
