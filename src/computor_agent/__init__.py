"""
Computor Agent - AI agents for course management.

This package provides AI agent capabilities for the Computor course
management system, including a tutor AI for grading student submissions.
"""

__version__ = "0.1.0"

from computor_agent.llm import (
    DummyProvider,
    DummyProviderConfig,
    LLMConfig,
    LLMProvider,
    LLMResponse,
    Message,
    MessageRole,
    OpenAIProvider,
    ProviderType,
    StreamChunk,
    create_provider,
    get_provider,
    list_providers,
)

__all__ = [
    # Version
    "__version__",
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
]
