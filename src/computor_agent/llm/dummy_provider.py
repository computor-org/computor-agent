"""
Dummy LLM provider for testing.

This provider returns static/configurable responses without making any
actual API calls. Useful for testing, development, and demonstrations.
"""

import asyncio
from typing import Any, AsyncIterator, Optional

from computor_agent.llm.base import LLMProvider, LLMResponse, StreamChunk
from computor_agent.llm.config import DummyProviderConfig, LLMConfig, Message
from computor_agent.llm.exceptions import LLMError


class DummyProvider(LLMProvider):
    """
    A dummy LLM provider for testing purposes.

    This provider returns configurable static responses, making it useful for:
    - Unit testing without API dependencies
    - Development and prototyping
    - Demonstrations
    - Testing error handling (can be configured to fail)

    Example:
        ```python
        config = LLMConfig(provider=ProviderType.DUMMY)
        dummy_config = DummyProviderConfig(
            response_text="Hello from dummy!",
            stream_chunks=["Hello ", "from ", "dummy!"],
        )
        provider = DummyProvider(config, dummy_config)

        # Complete call
        response = await provider.complete("Any prompt")
        print(response.content)  # "Hello from dummy!"

        # Streaming call
        async for chunk in provider.stream("Any prompt"):
            print(chunk.content, end="")  # "Hello from dummy!"
        ```
    """

    def __init__(
        self,
        config: LLMConfig,
        dummy_config: Optional[DummyProviderConfig] = None,
    ):
        """
        Initialize the dummy provider.

        Args:
            config: Base LLM configuration
            dummy_config: Dummy-specific configuration (uses defaults if not provided)
        """
        super().__init__(config)
        self.dummy_config = dummy_config or DummyProviderConfig()
        self._call_count = 0
        self._last_prompt: Optional[str | list[Message]] = None
        self._last_kwargs: dict[str, Any] = {}

    @property
    def call_count(self) -> int:
        """Get the number of times complete() or stream() was called."""
        return self._call_count

    @property
    def last_prompt(self) -> Optional[str | list[Message]]:
        """Get the last prompt that was passed to complete() or stream()."""
        return self._last_prompt

    @property
    def last_kwargs(self) -> dict[str, Any]:
        """Get the last kwargs that were passed to complete() or stream()."""
        return self._last_kwargs

    def reset_tracking(self) -> None:
        """Reset call tracking (useful between test cases)."""
        self._call_count = 0
        self._last_prompt = None
        self._last_kwargs = {}

    async def complete(
        self,
        prompt: str | list[Message],
        *,
        system_prompt: Optional[str] = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """
        Return a static response.

        The response text is configurable via DummyProviderConfig.response_text.

        Args:
            prompt: The input prompt (stored for testing inspection)
            system_prompt: Optional system prompt (ignored but stored)
            **kwargs: Additional parameters (ignored but stored)

        Returns:
            LLMResponse with the configured static text

        Raises:
            LLMError: If dummy_config.should_fail is True
        """
        self._call_count += 1
        self._last_prompt = prompt
        self._last_kwargs = {"system_prompt": system_prompt, **kwargs}

        # Simulate delay
        if self.dummy_config.delay_seconds > 0:
            await asyncio.sleep(self.dummy_config.delay_seconds)

        # Check if configured to fail
        if self.dummy_config.should_fail:
            raise LLMError(
                self.dummy_config.error_message,
                provider=self.provider_name,
                model=self.model_name,
            )

        return LLMResponse(
            content=self.dummy_config.response_text,
            model=self.config.model,
            finish_reason="stop",
            usage={
                "prompt_tokens": self._estimate_tokens(prompt),
                "completion_tokens": len(self.dummy_config.response_text.split()),
                "total_tokens": self._estimate_tokens(prompt)
                + len(self.dummy_config.response_text.split()),
            },
        )

    async def stream(
        self,
        prompt: str | list[Message],
        *,
        system_prompt: Optional[str] = None,
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]:
        """
        Stream static response chunks.

        The chunks are configurable via DummyProviderConfig.stream_chunks.

        Args:
            prompt: The input prompt (stored for testing inspection)
            system_prompt: Optional system prompt (ignored but stored)
            **kwargs: Additional parameters (ignored but stored)

        Yields:
            StreamChunk objects with the configured chunks

        Raises:
            LLMError: If dummy_config.should_fail is True, or after
                     fail_after_chunks chunks if configured
        """
        self._call_count += 1
        self._last_prompt = prompt
        self._last_kwargs = {"system_prompt": system_prompt, **kwargs}

        # Check if configured to fail immediately
        if self.dummy_config.should_fail:
            raise LLMError(
                self.dummy_config.error_message,
                provider=self.provider_name,
                model=self.model_name,
            )

        chunks = self.dummy_config.stream_chunks
        for i, chunk_text in enumerate(chunks):
            # Simulate delay between chunks
            if self.dummy_config.delay_seconds > 0:
                await asyncio.sleep(self.dummy_config.delay_seconds)

            # Check if configured to fail after N chunks
            if (
                self.dummy_config.fail_after_chunks is not None
                and i >= self.dummy_config.fail_after_chunks
            ):
                raise LLMError(
                    f"Simulated failure after {i} chunks",
                    provider=self.provider_name,
                    model=self.model_name,
                )

            is_final = i == len(chunks) - 1
            yield StreamChunk(
                content=chunk_text,
                finish_reason="stop" if is_final else None,
                is_final=is_final,
            )

    def _estimate_tokens(self, prompt: str | list[Message]) -> int:
        """Rough token estimation (words / 0.75)."""
        if isinstance(prompt, str):
            text = prompt
        else:
            text = " ".join(msg.content for msg in prompt)
        return int(len(text.split()) / 0.75)

    def set_response(self, text: str) -> None:
        """
        Convenience method to change the response text.

        Args:
            text: New response text for complete() calls
        """
        self.dummy_config.response_text = text

    def set_stream_chunks(self, chunks: list[str]) -> None:
        """
        Convenience method to change the stream chunks.

        Args:
            chunks: New list of chunks for stream() calls
        """
        self.dummy_config.stream_chunks = chunks

    def set_should_fail(self, should_fail: bool, error_message: Optional[str] = None) -> None:
        """
        Configure whether the provider should fail.

        Args:
            should_fail: If True, all calls will raise an error
            error_message: Optional custom error message
        """
        self.dummy_config.should_fail = should_fail
        if error_message:
            self.dummy_config.error_message = error_message
