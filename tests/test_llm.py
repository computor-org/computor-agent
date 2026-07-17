"""Tests for LLM providers."""

import base64

import pytest

from computor_agent.llm import (
    DummyProvider,
    DummyProviderConfig,
    ImageContent,
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


class TestImageContent:
    """Tests for ImageContent and multimodal messages."""

    PNG_BYTES = b"\x89PNG\r\n\x1a\nfake-image-data"

    def test_to_data_url(self):
        """Test base64 data URL encoding."""
        image = ImageContent(data=self.PNG_BYTES, media_type="image/png")
        expected = base64.b64encode(self.PNG_BYTES).decode("ascii")
        assert image.to_data_url() == f"data:image/png;base64,{expected}"

    def test_data_not_in_repr(self):
        """Image bytes must not leak into repr (log safety)."""
        image = ImageContent(data=self.PNG_BYTES, media_type="image/png")
        assert "fake-image-data" not in repr(image)

    def test_user_with_images(self):
        """Test creating a user message with images."""
        image = ImageContent(data=self.PNG_BYTES, media_type="image/png")
        msg = Message.user_with_images("Review this", [image])
        assert msg.role.value == "user"
        assert msg.content == "Review this"
        assert len(msg.images) == 1

    def test_message_defaults_to_no_images(self):
        """Plain messages have an empty images list."""
        assert Message.user("Hello").images == []


class TestPrepareMessagesMultimodal:
    """Tests for LLMProvider._prepare_messages with and without images."""

    @pytest.fixture
    def provider(self):
        config = LLMConfig(provider=ProviderType.DUMMY)
        return DummyProvider(config, DummyProviderConfig(delay_seconds=0))

    def test_text_only_unchanged(self, provider):
        """Text-only messages keep plain string content (regression)."""
        messages = provider._prepare_messages(
            [Message.user("Hello"), Message.assistant("Hi")],
            system_prompt="Be helpful",
        )
        assert messages == [
            {"role": "system", "content": "Be helpful"},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
        ]

    def test_string_prompt_unchanged(self, provider):
        """String prompts keep plain string content."""
        messages = provider._prepare_messages("Hello")
        assert messages == [{"role": "user", "content": "Hello"}]

    def test_message_with_image_uses_content_parts(self, provider):
        """Messages with images become OpenAI vision content-parts lists."""
        image = ImageContent(data=b"img-bytes", media_type="image/png")
        messages = provider._prepare_messages(
            [Message.user_with_images("Review this figure", [image])]
        )
        assert len(messages) == 1
        content = messages[0]["content"]
        assert content == [
            {"type": "text", "text": "Review this figure"},
            {"type": "image_url", "image_url": {"url": image.to_data_url()}},
        ]

    def test_multiple_images_one_part_each(self, provider):
        """Multiple images produce one image_url part each, text first."""
        images = [
            ImageContent(data=b"one", media_type="image/png"),
            ImageContent(data=b"two", media_type="image/jpeg"),
        ]
        messages = provider._prepare_messages(
            [Message.user_with_images("Two figures", images)]
        )
        content = messages[0]["content"]
        assert content[0] == {"type": "text", "text": "Two figures"}
        assert [p["type"] for p in content[1:]] == ["image_url", "image_url"]
        assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")
        assert content[2]["image_url"]["url"].startswith("data:image/jpeg;base64,")


class TestSanitizeMessagesForLog:
    """Tests for the debug-log image sanitizer."""

    def test_image_urls_truncated(self):
        from computor_agent.llm.openai_provider import _sanitize_messages_for_log

        long_url = "data:image/png;base64," + "A" * 10000
        messages = [
            {"role": "system", "content": "sys"},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "look"},
                    {"type": "image_url", "image_url": {"url": long_url}},
                ],
            },
        ]
        sanitized = _sanitize_messages_for_log(messages)
        # Original untouched, text parts untouched
        assert messages[1]["content"][1]["image_url"]["url"] == long_url
        assert sanitized[0] == {"role": "system", "content": "sys"}
        assert sanitized[1]["content"][0] == {"type": "text", "text": "look"}
        # Image URL truncated but annotated with original length
        logged_url = sanitized[1]["content"][1]["image_url"]["url"]
        assert len(logged_url) < 100
        assert f"({len(long_url)} chars)" in logged_url


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
    async def test_prompt_history(self, provider):
        """Test that every prompt is recorded in order."""
        await provider.complete("First")
        await provider.complete("Second")
        async for _ in provider.stream("Third"):
            pass
        assert provider.prompt_history == ["First", "Second", "Third"]

        provider.reset_tracking()
        assert provider.prompt_history == []
        assert provider.call_count == 0

    @pytest.mark.asyncio
    async def test_response_queue(self):
        """Test queued responses returned in call order, then fallback."""
        config = LLMConfig(provider=ProviderType.DUMMY)
        dummy_config = DummyProviderConfig(
            response_text="fallback",
            response_queue=["one", "two"],
            delay_seconds=0,
        )
        provider = DummyProvider(config, dummy_config)

        assert (await provider.complete("a")).content == "one"
        assert (await provider.complete("b")).content == "two"
        assert (await provider.complete("c")).content == "fallback"

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
