"""
LLM provider factory.

This module provides a factory for creating LLM providers based on configuration.
It supports registering custom providers and selecting providers by type.
"""

from typing import Callable, Optional, Type

from computor_agent.llm.base import LLMProvider
from computor_agent.llm.config import DummyProviderConfig, LLMConfig, ProviderType
from computor_agent.llm.dummy_provider import DummyProvider
from computor_agent.llm.exceptions import LLMProviderNotFoundError
from computor_agent.llm.openai_provider import OpenAIProvider


# Type alias for provider factory functions
ProviderFactory = Callable[[LLMConfig], LLMProvider]

# Registry of provider factories
_PROVIDER_REGISTRY: dict[ProviderType, ProviderFactory] = {}


def register_provider(
    provider_type: ProviderType,
    factory: Optional[ProviderFactory] = None,
) -> Callable[[ProviderFactory], ProviderFactory]:
    """
    Register a provider factory for a given provider type.

    Can be used as a decorator or called directly.

    Example:
        ```python
        # As decorator
        @register_provider(ProviderType.CUSTOM)
        def create_custom_provider(config: LLMConfig) -> LLMProvider:
            return CustomProvider(config)

        # Direct call
        register_provider(ProviderType.CUSTOM, create_custom_provider)
        ```

    Args:
        provider_type: The provider type to register
        factory: Optional factory function (if not using as decorator)

    Returns:
        The factory function (for decorator use)
    """

    def decorator(func: ProviderFactory) -> ProviderFactory:
        _PROVIDER_REGISTRY[provider_type] = func
        return func

    if factory is not None:
        return decorator(factory)
    return decorator


def get_provider(
    config: LLMConfig,
    *,
    dummy_config: Optional[DummyProviderConfig] = None,
) -> LLMProvider:
    """
    Create an LLM provider based on configuration.

    Args:
        config: LLM configuration specifying the provider type
        dummy_config: Optional configuration for dummy provider

    Returns:
        An LLMProvider instance

    Raises:
        LLMProviderNotFoundError: If the provider type is not registered

    Example:
        ```python
        # Create a provider from config
        config = LLMConfig(
            provider=ProviderType.LMSTUDIO,
            model="gpt-oss-120b",
            base_url="http://localhost:1234/v1",
        )
        provider = get_provider(config)

        # Use the provider
        response = await provider.complete("Hello!")
        ```
    """
    # Handle dummy provider specially (needs extra config)
    if config.provider == ProviderType.DUMMY:
        return DummyProvider(config, dummy_config)

    # Look up in registry
    factory = _PROVIDER_REGISTRY.get(config.provider)
    if factory is None:
        available = ", ".join(p.value for p in _PROVIDER_REGISTRY.keys())
        raise LLMProviderNotFoundError(
            f"Unknown provider type: {config.provider.value}. "
            f"Available providers: {available}",
            provider=config.provider.value,
        )

    return factory(config)


def create_provider(
    provider: str | ProviderType = ProviderType.LMSTUDIO,
    model: str = "gpt-oss-120b",
    base_url: str = "http://localhost:1234/v1",
    **kwargs,
) -> LLMProvider:
    """
    Convenience function to create a provider with common defaults.

    Args:
        provider: Provider type (string or enum)
        model: Model name/identifier
        base_url: API base URL
        **kwargs: Additional LLMConfig parameters

    Returns:
        An LLMProvider instance

    Example:
        ```python
        # Quick setup for LM Studio
        provider = create_provider(
            model="gpt-oss-120b",
            base_url="http://localhost:1234/v1",
        )

        # Quick setup for Ollama
        provider = create_provider(
            provider="ollama",
            model="devstral-small",
            base_url="http://localhost:11434/v1",
        )
        ```
    """
    if isinstance(provider, str):
        provider = ProviderType(provider)

    config = LLMConfig(
        provider=provider,
        model=model,
        base_url=base_url,
        **kwargs,
    )

    return get_provider(config)


# Register built-in providers
@register_provider(ProviderType.OPENAI)
def _create_openai_provider(config: LLMConfig) -> LLMProvider:
    """Create OpenAI provider."""
    return OpenAIProvider(config)


@register_provider(ProviderType.LMSTUDIO)
def _create_lmstudio_provider(config: LLMConfig) -> LLMProvider:
    """Create LM Studio provider (OpenAI-compatible)."""
    return OpenAIProvider(config)


@register_provider(ProviderType.OLLAMA)
def _create_ollama_provider(config: LLMConfig) -> LLMProvider:
    """Create Ollama provider (OpenAI-compatible)."""
    return OpenAIProvider(config)


def list_providers() -> list[str]:
    """
    List all registered provider types.

    Returns:
        List of provider type names
    """
    return [p.value for p in _PROVIDER_REGISTRY.keys()] + [ProviderType.DUMMY.value]


def is_provider_registered(provider_type: ProviderType) -> bool:
    """
    Check if a provider type is registered.

    Args:
        provider_type: The provider type to check

    Returns:
        True if the provider is registered
    """
    if provider_type == ProviderType.DUMMY:
        return True
    return provider_type in _PROVIDER_REGISTRY
