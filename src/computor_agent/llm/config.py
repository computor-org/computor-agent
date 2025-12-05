"""
LLM configuration models.

This module provides Pydantic models for configuring LLM providers.
Supports multiple backends (OpenAI, LM Studio, Ollama) with extensive customization.
"""

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator


class ProviderType(str, Enum):
    """Supported LLM provider types."""

    OPENAI = "openai"
    OLLAMA = "ollama"
    LMSTUDIO = "lmstudio"
    DUMMY = "dummy"


class MessageRole(str, Enum):
    """Message roles for chat completions."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class Message(BaseModel):
    """A single message in a conversation."""

    role: MessageRole
    content: str

    @classmethod
    def system(cls, content: str) -> "Message":
        """Create a system message."""
        return cls(role=MessageRole.SYSTEM, content=content)

    @classmethod
    def user(cls, content: str) -> "Message":
        """Create a user message."""
        return cls(role=MessageRole.USER, content=content)

    @classmethod
    def assistant(cls, content: str) -> "Message":
        """Create an assistant message."""
        return cls(role=MessageRole.ASSISTANT, content=content)


class LLMConfig(BaseModel):
    """
    Configuration for an LLM provider.

    This configuration supports multiple provider types and can be customized
    extensively for different use cases.

    Example:
        ```python
        # For LM Studio with local model
        config = LLMConfig(
            provider=ProviderType.LMSTUDIO,
            model="gpt-oss-120b",
            base_url="http://localhost:1234/v1",
        )

        # For Ollama
        config = LLMConfig(
            provider=ProviderType.OLLAMA,
            model="devstral-small",
            base_url="http://localhost:11434/v1",
        )

        # For OpenAI
        config = LLMConfig(
            provider=ProviderType.OPENAI,
            model="gpt-4",
            api_key="sk-...",
        )
        ```
    """

    # Provider settings
    provider: ProviderType = Field(
        default=ProviderType.LMSTUDIO,
        description="The LLM provider type to use",
    )
    model: str = Field(
        default="gpt-oss-120b",
        description="Model identifier/name",
    )
    base_url: str = Field(
        default="http://localhost:1234/v1",
        description="Base URL for the API endpoint",
    )
    api_key: Optional[SecretStr] = Field(
        default=None,
        description="API key for authentication (required for some providers)",
    )

    # Generation parameters
    temperature: float = Field(
        default=0.7,
        ge=0.0,
        le=2.0,
        description="Sampling temperature (0.0 = deterministic, higher = more random)",
    )
    max_tokens: Optional[int] = Field(
        default=None,
        gt=0,
        description="Maximum tokens to generate (None = model default)",
    )
    top_p: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Nucleus sampling parameter",
    )
    top_k: Optional[int] = Field(
        default=None,
        gt=0,
        description="Top-k sampling parameter",
    )
    frequency_penalty: Optional[float] = Field(
        default=None,
        ge=-2.0,
        le=2.0,
        description="Frequency penalty for repetition",
    )
    presence_penalty: Optional[float] = Field(
        default=None,
        ge=-2.0,
        le=2.0,
        description="Presence penalty for repetition",
    )
    stop_sequences: Optional[list[str]] = Field(
        default=None,
        description="Stop sequences to end generation",
    )
    seed: Optional[int] = Field(
        default=None,
        description="Random seed for reproducibility",
    )

    # Request settings
    timeout: float = Field(
        default=120.0,
        gt=0,
        description="Request timeout in seconds",
    )
    max_retries: int = Field(
        default=3,
        ge=0,
        description="Maximum number of retry attempts",
    )

    # System prompt
    system_prompt: Optional[str] = Field(
        default=None,
        description="Default system prompt to prepend to conversations",
    )

    # Extra provider-specific options
    extra_options: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional provider-specific options",
    )

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, v: str) -> str:
        """Ensure base_url doesn't have trailing slash."""
        return v.rstrip("/")

    @model_validator(mode="after")
    def validate_provider_requirements(self) -> "LLMConfig":
        """Validate provider-specific requirements."""
        if self.provider == ProviderType.OPENAI and not self.api_key:
            # OpenAI requires an API key, but we allow None for validation
            # The provider will raise an error at runtime if key is missing
            pass
        return self

    def get_api_key(self) -> Optional[str]:
        """Get the API key as a plain string."""
        if self.api_key:
            return self.api_key.get_secret_value()
        return None

    def to_generation_params(self) -> dict[str, Any]:
        """
        Convert config to generation parameters dict.

        Returns only non-None generation parameters suitable for API calls.
        """
        params: dict[str, Any] = {
            "model": self.model,
            "temperature": self.temperature,
        }

        if self.max_tokens is not None:
            params["max_tokens"] = self.max_tokens
        if self.top_p is not None:
            params["top_p"] = self.top_p
        if self.frequency_penalty is not None:
            params["frequency_penalty"] = self.frequency_penalty
        if self.presence_penalty is not None:
            params["presence_penalty"] = self.presence_penalty
        if self.stop_sequences is not None:
            params["stop"] = self.stop_sequences
        if self.seed is not None:
            params["seed"] = self.seed

        # Add any extra options
        params.update(self.extra_options)

        return params

    def with_overrides(self, **kwargs: Any) -> "LLMConfig":
        """
        Create a new config with the specified overrides.

        Args:
            **kwargs: Fields to override

        Returns:
            New LLMConfig with overrides applied
        """
        data = self.model_dump()
        data.update(kwargs)
        return LLMConfig.model_validate(data)


class DummyProviderConfig(BaseModel):
    """Configuration specific to the dummy provider for testing."""

    response_text: str = Field(
        default="This is a dummy response for testing purposes.",
        description="Static text to return for complete() calls",
    )
    stream_chunks: list[str] = Field(
        default_factory=lambda: [
            "This ",
            "is ",
            "a ",
            "streaming ",
            "dummy ",
            "response.",
        ],
        description="List of chunks to yield for stream() calls",
    )
    delay_seconds: float = Field(
        default=0.1,
        ge=0.0,
        description="Artificial delay between operations (for simulating latency)",
    )
    fail_after_chunks: Optional[int] = Field(
        default=None,
        description="If set, raise an error after this many stream chunks (for testing error handling)",
    )
    should_fail: bool = Field(
        default=False,
        description="If True, all calls will raise an error (for testing error handling)",
    )
    error_message: str = Field(
        default="Simulated dummy provider error",
        description="Error message to raise when should_fail is True",
    )
