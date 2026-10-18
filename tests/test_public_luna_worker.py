"""Synthetic network boundary tests for the outbound-only Lena worker."""

import json

import httpx
import pytest

from computor_agent.public_luna_worker import (
    FALLBACK_ANSWER,
    MAX_CLAIM_RESPONSE_BYTES,
    _bounded_json,
    _model_body,
    _validate_config,
    process_one,
)

REQUEST = {
    "course_content_id": "00000000-0000-0000-0000-000000000001",
    "assignment": "Explain a loop",
    "question": "Why is my answer empty?",
    "submitted_text": "for x in []: print(x)",
}


def test_only_explicit_bounded_text_reaches_model():
    body = _model_body(REQUEST)
    assert body["model"] == "luna-public"
    assert body["messages"][0]["content"].startswith("You are Lena,")
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
    with pytest.raises(ValueError):
        _validate_config("https://computor.example", "http://10.77.0.20:8080", "a" * 32, "a" * 32)
    with pytest.raises(ValueError):
        _validate_config("https://computor.example?token=x", "http://10.77.0.20:8080", "a" * 32, "b" * 32)


@pytest.mark.asyncio
async def test_streaming_limit_stops_reading_and_closes_response():
    class OversizedStream(httpx.AsyncByteStream):
        closed = False

        async def __aiter__(self):
            yield b"x" * 4096
            yield b"x"
            pytest.fail("Read beyond the bounded response")

        async def aclose(self):
            self.closed = True

    stream = OversizedStream()
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, stream=stream))
    ) as client:
        with pytest.raises(ValueError, match="Response too large"):
            await _bounded_json(client, "https://computor.example", headers={}, max_bytes=4096)
    assert stream.closed


@pytest.mark.asyncio
async def test_claim_accepts_maximum_unicode_context():
    request = {**REQUEST, "assignment": "😀" * 2000, "question": "😀" * 6000,
               "submitted_text": "😀" * 16000}
    claim = {"id": "00000000-0000-0000-0000-000000000002", "lease": "7", "request": request}
    encoded = json.dumps(claim, ensure_ascii=False).encode()
    assert 65536 < len(encoded) < MAX_CLAIM_RESPONSE_BYTES
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=encoded))
    ) as client:
        actual = await _bounded_json(client, "https://computor.example", headers={},
                                     max_bytes=MAX_CLAIM_RESPONSE_BYTES)
    assert actual == claim
    _model_body(actual["request"])


@pytest.mark.asyncio
async def test_success_sends_one_answer_without_general_api_token():
    seen = []

    def model_handler(request):
        seen.append(("model", request))
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "Try an input item."}, "finish_reason": "stop"}]
            },
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
    assert seen[1][1].headers["X-Public-Luna-Worker-Key"] == "a" * 32
    assert seen[1][1].url.path == "/public-luna/worker/complete/00000000-0000-0000-0000-000000000002"
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


REASONING = "We need answer to user in English. Need analyze user request. Could be R?"


async def _completion_for(model_json: dict) -> dict:
    results = []

    def model_handler(_request):
        return httpx.Response(200, json=model_json)

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
    assert len(results) == 1
    return results[0]


def _choice(finish_reason, content, reasoning=None):
    message = {"role": "assistant", "content": content}
    if reasoning is not None:
        message["reasoning_content"] = reasoning
    return {"choices": [{"message": message, "finish_reason": finish_reason}]}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("model_json", "expected"),
    [
        # issues#465: budget exhausted while reasoning, reasoning returned as content.
        (_choice("length", REASONING), FALLBACK_ANSWER),
        # Budget exhausted after reasoning: the answer is cut off mid-sentence.
        (_choice("length", "Use `color=` and then", REASONING), FALLBACK_ANSWER),
        (_choice("stop", None, REASONING), FALLBACK_ANSWER),
        (_choice("stop", "<think>" + REASONING), FALLBACK_ANSWER),
        (_choice("stop", "<think>" + REASONING + "</think>"), FALLBACK_ANSWER),
        (_choice(None, "Use `color=`."), FALLBACK_ANSWER),
        (_choice("stop", "Use `color=`.", REASONING), "Use `color=`."),
        (_choice("stop", "<think>" + REASONING + "</think>\n\nUse `color=`."), "Use `color=`."),
        (_choice("stop", REASONING + "</think>\nUse `color=`."), "Use `color=`."),
        (_choice("stop", "x" * 8193), FALLBACK_ANSWER),
    ],
)
async def test_only_final_answer_reaches_students(model_json, expected):
    result = await _completion_for(model_json)
    assert result == {"lease": "7", "state": "done", "answer": expected}
    assert "Need analyze" not in result["answer"]


@pytest.mark.asyncio
async def test_malformed_model_response_is_a_generic_failure():
    result = await _completion_for({"choices": []})
    assert result == {"lease": "7", "state": "failed", "answer": ""}
