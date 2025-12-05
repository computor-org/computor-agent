"""
Abstract base class for LLM providers.

This module defines the interface that all LLM providers must implement.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Optional

from computor_agent.llm.config import LLMConfig, Message


@dataclass
class LLMResponse:
    """
    Response from an LLM completion request.

    Attributes:
        content: The generated text content
        model: The model that generated the response
        finish_reason: Why generation stopped (e.g., "stop", "length", "content_filter")
        usage: Token usage statistics (if available)
        raw_response: The raw response from the provider (for debugging)
    """

    content: str
    model: str
    finish_reason: Optional[str] = None
    usage: Optional[dict[str, int]] = None
    raw_response: Optional[dict[str, Any]] = field(default=None, repr=False)

    @property
    def prompt_tokens(self) -> Optional[int]:
        """Get the number of prompt tokens used."""
        if self.usage:
            return self.usage.get("prompt_tokens")
        return None

    @property
    def completion_tokens(self) -> Optional[int]:
        """Get the number of completion tokens generated."""
        if self.usage:
            return self.usage.get("completion_tokens")
        return None

    @property
    def total_tokens(self) -> Optional[int]:
        """Get the total number of tokens used."""
        if self.usage:
            return self.usage.get("total_tokens")
        return None


@dataclass
class StreamChunk:
    """
    A single chunk from a streaming LLM response.

    Attributes:
        content: The text content of this chunk
        finish_reason: Set on the final chunk to indicate why generation stopped
        is_final: Whether this is the last chunk
    """

    content: str
    finish_reason: Optional[str] = None
    is_final: bool = False


class LLMProvider(ABC):
    """
    Abstract base class for LLM providers.

    All LLM providers must implement this interface to ensure consistent
    behavior across different backends (OpenAI, Ollama, LM Studio, etc.).

    Example:
        ```python
        class MyProvider(LLMProvider):
            async def complete(self, prompt, **kwargs) -> LLMResponse:
                # Implementation
                pass

            async def stream(self, prompt, **kwargs) -> AsyncIterator[StreamChunk]:
                # Implementation
                yield StreamChunk(content="Hello")
        ```
    """

    def __init__(self, config: LLMConfig):
        """
        Initialize the provider with configuration.

        Args:
            config: LLM configuration settings
        """
        self.config = config

    @property
    def provider_name(self) -> str:
        """Get the provider name."""
        return self.config.provider.value

    @property
    def model_name(self) -> str:
        """Get the model name."""
        return self.config.model

    @abstractmethod
    async def complete(
        self,
        prompt: str | list[Message],
        *,
        system_prompt: Optional[str] = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """
        Generate a complete response from the LLM.

        This method sends a prompt to the LLM and waits for the complete
        response before returning.

        Args:
            prompt: The input prompt (string or list of messages)
            system_prompt: Optional system prompt to override config default
            **kwargs: Additional generation parameters to override config

        Returns:
            LLMResponse containing the generated text and metadata

        Raises:
            LLMConnectionError: If connection to the provider fails
            LLMAuthenticationError: If authentication fails
            LLMRateLimitError: If rate limit is exceeded
            LLMTimeoutError: If the request times out
            LLMResponseError: If the response is invalid
            LLMModelNotFoundError: If the model doesn't exist
            LLMContextLengthError: If input is too long
        """
        ...

    @abstractmethod
    async def stream(
        self,
        prompt: str | list[Message],
        *,
        system_prompt: Optional[str] = None,
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]:
        """
        Stream a response from the LLM chunk by chunk.

        This method sends a prompt to the LLM and yields response chunks
        as they become available, allowing for real-time display.

        Args:
            prompt: The input prompt (string or list of messages)
            system_prompt: Optional system prompt to override config default
            **kwargs: Additional generation parameters to override config

        Yields:
            StreamChunk objects containing partial response text

        Raises:
            LLMConnectionError: If connection to the provider fails
            LLMAuthenticationError: If authentication fails
            LLMRateLimitError: If rate limit is exceeded
            LLMTimeoutError: If the request times out
            LLMResponseError: If the response is invalid
            LLMModelNotFoundError: If the model doesn't exist
            LLMContextLengthError: If input is too long

        Example:
            ```python
            async for chunk in provider.stream("Hello, world!"):
                print(chunk.content, end="", flush=True)
                if chunk.is_final:
                    print()  # Newline at the end
            ```
        """
        ...

    def _prepare_messages(
        self,
        prompt: str | list[Message],
        system_prompt: Optional[str] = None,
    ) -> list[dict[str, str]]:
        """
        Prepare messages for the API request.

        Converts the prompt to a list of message dicts, optionally
        prepending a system prompt.

        Args:
            prompt: User prompt (string or list of Message objects)
            system_prompt: Optional system prompt (overrides config default)

        Returns:
            List of message dicts ready for API call
        """
        messages: list[dict[str, str]] = []

        # Add system prompt if provided or from config
        effective_system_prompt = system_prompt or self.config.system_prompt
        if effective_system_prompt:
            messages.append({"role": "system", "content": effective_system_prompt})

        # Handle prompt
        if isinstance(prompt, str):
            messages.append({"role": "user", "content": prompt})
        else:
            for msg in prompt:
                messages.append({"role": msg.role.value, "content": msg.content})

        return messages

    def _merge_generation_params(self, **kwargs: Any) -> dict[str, Any]:
        """
        Merge config generation params with call-time overrides.

        Args:
            **kwargs: Override parameters

        Returns:
            Merged generation parameters
        """
        params = self.config.to_generation_params()

        # Override with any provided kwargs (only if not None)
        for key, value in kwargs.items():
            if value is not None:
                params[key] = value

        return params

    async def close(self) -> None:
        """
        Close any resources held by the provider.

        Subclasses should override this to clean up HTTP clients, etc.
        """
        pass

    async def __aenter__(self) -> "LLMProvider":
        """Enter async context manager."""
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit async context manager."""
        await self.close()

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(provider={self.provider_name}, model={self.model_name})"
