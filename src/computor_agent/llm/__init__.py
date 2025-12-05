"""
LLM provider abstraction layer.

This module provides a unified interface for interacting with various
LLM providers (OpenAI, LM Studio, Ollama, etc.).

Example:
    ```python
    from computor_agent.llm import create_provider, LLMConfig, ProviderType

    # Quick setup
    provider = create_provider(
        model="gpt-oss-120b",
        base_url="http://localhost:1234/v1",
    )

    # Or with full config
    config = LLMConfig(
        provider=ProviderType.LMSTUDIO,
        model="gpt-oss-120b",
        base_url="http://localhost:1234/v1",
        temperature=0.7,
    )
    provider = get_provider(config)

    # Complete response
    response = await provider.complete("What is Python?")
    print(response.content)

    # Streaming response
    async for chunk in provider.stream("Explain async/await"):
        print(chunk.content, end="")
    ```
"""

from computor_agent.llm.base import LLMProvider, LLMResponse, StreamChunk
from computor_agent.llm.config import (
    DummyProviderConfig,
    LLMConfig,
    Message,
    MessageRole,
    ProviderType,
)
from computor_agent.llm.dummy_provider import DummyProvider
from computor_agent.llm.exceptions import (
    LLMAuthenticationError,
    LLMConfigurationError,
    LLMConnectionError,
    LLMContentFilterError,
    LLMContextLengthError,
    LLMError,
    LLMModelNotFoundError,
    LLMProviderNotFoundError,
    LLMRateLimitError,
    LLMResponseError,
    LLMTimeoutError,
)
from computor_agent.llm.factory import (
    create_provider,
    get_provider,
    is_provider_registered,
    list_providers,
    register_provider,
)
from computor_agent.llm.openai_provider import OpenAIProvider

__all__ = [
    # Config
    "LLMConfig",
    "DummyProviderConfig",
    "ProviderType",
    "Message",
    "MessageRole",
    # Base classes
    "LLMProvider",
    "LLMResponse",
    "StreamChunk",
    # Providers
    "OpenAIProvider",
    "DummyProvider",
    # Factory
    "get_provider",
    "create_provider",
    "list_providers",
    "register_provider",
    "is_provider_registered",
    # Exceptions
    "LLMError",
    "LLMConnectionError",
    "LLMAuthenticationError",
    "LLMRateLimitError",
    "LLMTimeoutError",
    "LLMResponseError",
    "LLMModelNotFoundError",
    "LLMContextLengthError",
    "LLMContentFilterError",
    "LLMProviderNotFoundError",
    "LLMConfigurationError",
]
