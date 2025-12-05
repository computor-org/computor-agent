"""
LLM-specific exceptions.

This module defines exceptions that can occur when interacting with LLM providers.
"""

from typing import Any, Optional


class LLMError(Exception):
    """Base exception for all LLM-related errors."""

    def __init__(
        self,
        message: str,
        *,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.message = message
        self.provider = provider
        self.model = model
        self.details = details or {}

    def __str__(self) -> str:
        parts = [self.message]
        if self.provider:
            parts.append(f"provider={self.provider}")
        if self.model:
            parts.append(f"model={self.model}")
        return " ".join(parts)


class LLMConnectionError(LLMError):
    """Raised when connection to the LLM provider fails."""

    pass


class LLMAuthenticationError(LLMError):
    """Raised when authentication with the LLM provider fails."""

    pass


class LLMRateLimitError(LLMError):
    """Raised when rate limit is exceeded."""

    def __init__(
        self,
        message: str,
        *,
        retry_after: Optional[float] = None,
        **kwargs: Any,
    ):
        super().__init__(message, **kwargs)
        self.retry_after = retry_after


class LLMTimeoutError(LLMError):
    """Raised when a request to the LLM provider times out."""

    pass


class LLMResponseError(LLMError):
    """Raised when the LLM provider returns an invalid or unexpected response."""

    def __init__(
        self,
        message: str,
        *,
        status_code: Optional[int] = None,
        response_body: Optional[str] = None,
        **kwargs: Any,
    ):
        super().__init__(message, **kwargs)
        self.status_code = status_code
        self.response_body = response_body


class LLMModelNotFoundError(LLMError):
    """Raised when the requested model is not available."""

    pass


class LLMContextLengthError(LLMError):
    """Raised when the input exceeds the model's context length."""

    def __init__(
        self,
        message: str,
        *,
        max_tokens: Optional[int] = None,
        requested_tokens: Optional[int] = None,
        **kwargs: Any,
    ):
        super().__init__(message, **kwargs)
        self.max_tokens = max_tokens
        self.requested_tokens = requested_tokens


class LLMContentFilterError(LLMError):
    """Raised when content is blocked by safety filters."""

    pass


class LLMProviderNotFoundError(LLMError):
    """Raised when the requested provider type is not registered."""

    pass


class LLMConfigurationError(LLMError):
    """Raised when there's an error in the LLM configuration."""

    pass
