"""Smoke tests for the AgentRuntime bootstrap."""

from computor_agent.runtime import AgentRuntime, RuntimeOptions
from computor_agent.runtime.auth import get_ws_token, make_token_provider
from computor_agent.settings.config import ComputorConfig
from computor_agent.tutor import TutorLLMAdapter

API_TOKEN = "ctp_" + "a" * 32


def make_config(with_llm=True, with_token=True, extra=None) -> ComputorConfig:
    data = {
        "backend": (
            {"url": "https://api.example.com", "api_token": API_TOKEN}
            if with_token
            else {"url": "https://api.example.com", "username": "u", "password": "p"}
        ),
    }
    if with_llm:
        data["llm"] = {
            "provider": "dummy",
            "model": "test-model",
            "base_url": "http://localhost:9999/v1",
        }
    if extra:
        data.update(extra)
    return ComputorConfig.from_dict(data)


class StubAuthProvider:
    def __init__(self, access_token=None):
        self._access_token = access_token

    async def get_access_token(self):
        return self._access_token

    async def refresh_token(self):
        return None


class StubClient:
    def __init__(self, access_token=None):
        self._auth_provider = StubAuthProvider(access_token)


async def test_run_returns_1_without_llm_config():
    runtime = AgentRuntime(make_config(with_llm=False), RuntimeOptions())
    assert await runtime.run() == 1


async def test_build_scheduler_with_api_token():
    runtime = AgentRuntime(make_config(), RuntimeOptions(dry_run=True))
    assert runtime._build_llm() is True

    tutor_llm = TutorLLMAdapter(runtime.llm_provider)
    scheduler = await runtime._build_scheduler(StubClient(), tutor_llm)

    assert scheduler is not None
    assert runtime.scheduler_stats.get_stats()["running"] is False


async def test_build_scheduler_without_token_fails_cleanly():
    runtime = AgentRuntime(make_config(with_token=False), RuntimeOptions())
    assert runtime._build_llm() is True

    tutor_llm = TutorLLMAdapter(runtime.llm_provider)
    scheduler = await runtime._build_scheduler(StubClient(access_token=None), tutor_llm)

    assert scheduler is None


async def test_build_vision_llm_disabled_by_default():
    runtime = AgentRuntime(make_config(), RuntimeOptions())
    assert runtime._build_llm() is True
    assert runtime._build_vision_llm() is True
    assert runtime.figure_reviewer is None


async def test_build_vision_llm_fails_fast_without_source():
    config = make_config(extra={"tutor": {"figure_review": {"enabled": True}}})
    runtime = AgentRuntime(config, RuntimeOptions())
    assert runtime._build_llm() is True
    assert runtime._build_vision_llm() is False


async def test_build_vision_llm_reuses_main_provider():
    config = make_config(
        extra={"tutor": {"figure_review": {"enabled": True, "use_agent_llm": True}}}
    )
    runtime = AgentRuntime(config, RuntimeOptions())
    assert runtime._build_llm() is True
    assert runtime._build_vision_llm() is True
    assert runtime.figure_reviewer.provider is runtime.llm_provider


async def test_build_vision_llm_dedicated_provider():
    config = make_config(
        extra={
            "vision_llm": {"provider": "dummy", "model": "vision-model"},
            "tutor": {"figure_review": {"enabled": True}},
        }
    )
    runtime = AgentRuntime(config, RuntimeOptions())
    assert runtime._build_llm() is True
    assert runtime._build_vision_llm() is True
    assert runtime.figure_reviewer.provider is not runtime.llm_provider
    assert runtime.figure_reviewer.provider.model_name == "vision-model"


async def test_get_ws_token_prefers_static_api_token():
    config = make_config()
    token = await get_ws_token(StubClient(access_token="session-token"), config.backend)
    assert token == API_TOKEN


async def test_get_ws_token_falls_back_to_session():
    config = make_config(with_token=False)
    token = await get_ws_token(StubClient(access_token="session-token"), config.backend)
    assert token == "session-token"


async def test_token_provider_returns_static_token():
    config = make_config()
    provider = make_token_provider(StubClient(), config.backend)
    assert await provider() == API_TOKEN
