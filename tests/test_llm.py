"""Tests for LLM providers."""

import pytest

from computor_agent.llm import (
    DummyProvider,
    DummyProviderConfig,
    LLMConfig,
    LLMResponse,
    Message,
    ProviderType,
    StreamChunk,
    create_provider,
    get_provider,
    list_providers,
)
from computor_agent.llm.exceptions import LLMError


class TestLLMConfig:
    """Tests for LLMConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = LLMConfig()
        assert config.provider == ProviderType.LMSTUDIO
        assert config.model == "gpt-oss-120b"
        assert config.temperature == 0.7
        assert config.base_url == "http://localhost:1234/v1"

    def test_custom_config(self):
        """Test custom configuration."""
        config = LLMConfig(
            provider=ProviderType.OLLAMA,
            model="devstral-small",
            base_url="http://localhost:11434/v1",
            temperature=0.5,
            max_tokens=1000,
        )
        assert config.provider == ProviderType.OLLAMA
        assert config.model == "devstral-small"
        assert config.temperature == 0.5
        assert config.max_tokens == 1000

    def test_base_url_trailing_slash_removed(self):
        """Test that trailing slash is removed from base_url."""
        config = LLMConfig(base_url="http://localhost:1234/v1/")
        assert config.base_url == "http://localhost:1234/v1"

    def test_to_generation_params(self):
        """Test generation params extraction."""
        config = LLMConfig(
            model="test-model",
            temperature=0.8,
            max_tokens=500,
            top_p=0.9,
        )
        params = config.to_generation_params()
        assert params["model"] == "test-model"
        assert params["temperature"] == 0.8
        assert params["max_tokens"] == 500
        assert params["top_p"] == 0.9

    def test_with_overrides(self):
        """Test creating new config with overrides."""
        config = LLMConfig(temperature=0.5)
        new_config = config.with_overrides(temperature=0.9, max_tokens=100)
        assert config.temperature == 0.5  # Original unchanged
        assert new_config.temperature == 0.9
        assert new_config.max_tokens == 100


class TestMessage:
    """Tests for Message class."""

    def test_system_message(self):
        """Test creating system message."""
        msg = Message.system("You are helpful")
        assert msg.role.value == "system"
        assert msg.content == "You are helpful"

    def test_user_message(self):
        """Test creating user message."""
        msg = Message.user("Hello")
        assert msg.role.value == "user"
        assert msg.content == "Hello"

    def test_assistant_message(self):
        """Test creating assistant message."""
        msg = Message.assistant("Hi there")
        assert msg.role.value == "assistant"
        assert msg.content == "Hi there"


class TestDummyProvider:
    """Tests for DummyProvider."""

    @pytest.fixture
    def provider(self):
        """Create a dummy provider for tests."""
        config = LLMConfig(provider=ProviderType.DUMMY)
        dummy_config = DummyProviderConfig(
            response_text="Test response",
            stream_chunks=["Hello ", "World!"],
            delay_seconds=0,
        )
        return DummyProvider(config, dummy_config)

    @pytest.mark.asyncio
    async def test_complete(self, provider):
        """Test complete() returns configured response."""
        response = await provider.complete("Any prompt")
        assert isinstance(response, LLMResponse)
        assert response.content == "Test response"
        assert response.finish_reason == "stop"

    @pytest.mark.asyncio
    async def test_stream(self, provider):
        """Test stream() yields configured chunks."""
        chunks = []
        async for chunk in provider.stream("Any prompt"):
            chunks.append(chunk)

        assert len(chunks) == 2
        assert chunks[0].content == "Hello "
        assert chunks[1].content == "World!"
        assert chunks[1].is_final

    @pytest.mark.asyncio
    async def test_call_tracking(self, provider):
        """Test that calls are tracked."""
        assert provider.call_count == 0

        await provider.complete("First")
        assert provider.call_count == 1
        assert provider.last_prompt == "First"

        async for _ in provider.stream("Second"):
            pass
        assert provider.call_count == 2
        assert provider.last_prompt == "Second"

    @pytest.mark.asyncio
    async def test_should_fail(self, provider):
        """Test error simulation."""
        provider.set_should_fail(True, "Test error")

        with pytest.raises(LLMError) as exc_info:
            await provider.complete("Any prompt")
        assert "Test error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_stream_fail_after_chunks(self):
        """Test failing after N chunks."""
        config = LLMConfig(provider=ProviderType.DUMMY)
        dummy_config = DummyProviderConfig(
            stream_chunks=["A", "B", "C", "D"],
            fail_after_chunks=2,
            delay_seconds=0,
        )
        provider = DummyProvider(config, dummy_config)

        chunks = []
        with pytest.raises(LLMError):
            async for chunk in provider.stream("Any"):
                chunks.append(chunk.content)

        assert len(chunks) == 2
        assert chunks == ["A", "B"]


class TestFactory:
    """Tests for provider factory."""

    def test_list_providers(self):
        """Test listing available providers."""
        providers = list_providers()
        assert "lmstudio" in providers
        assert "ollama" in providers
        assert "openai" in providers
        assert "dummy" in providers

    def test_get_dummy_provider(self):
        """Test creating dummy provider via factory."""
        config = LLMConfig(provider=ProviderType.DUMMY)
        provider = get_provider(config)
        assert isinstance(provider, DummyProvider)

    def test_create_provider_convenience(self):
        """Test create_provider convenience function."""
        provider = create_provider(
            provider="dummy",
            model="test",
        )
        assert isinstance(provider, DummyProvider)

    def test_get_provider_lmstudio(self):
        """Test creating LM Studio provider."""
        config = LLMConfig(
            provider=ProviderType.LMSTUDIO,
            model="test-model",
        )
        provider = get_provider(config)
        assert provider.provider_name == "lmstudio"
        assert provider.model_name == "test-model"


class TestLLMResponse:
    """Tests for LLMResponse dataclass."""

    def test_response_properties(self):
        """Test response properties."""
        response = LLMResponse(
            content="Hello",
            model="test-model",
            finish_reason="stop",
            usage={
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
            },
        )

        assert response.content == "Hello"
        assert response.prompt_tokens == 10
        assert response.completion_tokens == 5
        assert response.total_tokens == 15

    def test_response_without_usage(self):
        """Test response without usage info."""
        response = LLMResponse(
            content="Hello",
            model="test-model",
        )

        assert response.prompt_tokens is None
        assert response.completion_tokens is None
        assert response.total_tokens is None


class TestStreamChunk:
    """Tests for StreamChunk dataclass."""

    def test_chunk_properties(self):
        """Test chunk properties."""
        chunk = StreamChunk(
            content="Hello",
            finish_reason="stop",
            is_final=True,
        )

        assert chunk.content == "Hello"
        assert chunk.finish_reason == "stop"
        assert chunk.is_final is True

    def test_intermediate_chunk(self):
        """Test intermediate chunk."""
        chunk = StreamChunk(content="partial")

        assert chunk.content == "partial"
        assert chunk.finish_reason is None
        assert chunk.is_final is False
