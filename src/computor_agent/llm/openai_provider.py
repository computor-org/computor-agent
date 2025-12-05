"""
OpenAI-compatible LLM provider.

This provider works with any OpenAI-compatible API, including:
- OpenAI API
- LM Studio (local)
- Ollama (with OpenAI compatibility endpoint)
- vLLM
- text-generation-inference
- LocalAI
- Any other OpenAI-compatible server
"""

import json
import logging
from typing import Any, AsyncIterator, Optional

import httpx

from computor_agent.llm.base import LLMProvider, LLMResponse, StreamChunk
from computor_agent.llm.config import LLMConfig, Message
from computor_agent.llm.exceptions import (
    LLMAuthenticationError,
    LLMConnectionError,
    LLMContextLengthError,
    LLMModelNotFoundError,
    LLMRateLimitError,
    LLMResponseError,
    LLMTimeoutError,
)

logger = logging.getLogger(__name__)


class OpenAIProvider(LLMProvider):
    """
    OpenAI-compatible LLM provider.

    This provider uses the OpenAI chat completions API format, which is
    supported by many local and cloud LLM servers.

    Example:
        ```python
        # For LM Studio
        config = LLMConfig(
            provider=ProviderType.LMSTUDIO,
            model="gpt-oss-120b",
            base_url="http://localhost:1234/v1",
        )
        provider = OpenAIProvider(config)

        # Complete
        response = await provider.complete("What is Python?")
        print(response.content)

        # Stream
        async for chunk in provider.stream("Explain async/await"):
            print(chunk.content, end="", flush=True)
        ```
    """

    def __init__(self, config: LLMConfig):
        """
        Initialize the OpenAI-compatible provider.

        Args:
            config: LLM configuration with base_url, model, etc.
        """
        super().__init__(config)
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.config.base_url,
                timeout=httpx.Timeout(self.config.timeout),
                headers=self._build_headers(),
            )
        return self._client

    def _build_headers(self) -> dict[str, str]:
        """Build request headers."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        api_key = self.config.get_api_key()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        return headers

    def _handle_error_response(self, response: httpx.Response) -> None:
        """Convert HTTP error responses to appropriate exceptions."""
        status_code = response.status_code

        try:
            error_data = response.json()
            error = error_data.get("error", {})
            if isinstance(error, str):
                detail = error
                error_type = None
            else:
                detail = error.get("message", str(error_data))
                error_type = error.get("type")
        except Exception:
            detail = response.text or f"HTTP {status_code}"
            error_type = None

        common_kwargs = {
            "provider": self.provider_name,
            "model": self.model_name,
        }

        if status_code == 401:
            raise LLMAuthenticationError(detail, **common_kwargs)
        elif status_code == 404:
            raise LLMModelNotFoundError(
                f"Model '{self.config.model}' not found: {detail}",
                **common_kwargs,
            )
        elif status_code == 429:
            retry_after = response.headers.get("Retry-After")
            raise LLMRateLimitError(
                detail,
                retry_after=float(retry_after) if retry_after else None,
                **common_kwargs,
            )
        elif status_code == 400:
            # Check for context length errors
            if error_type == "context_length_exceeded" or "context" in detail.lower():
                raise LLMContextLengthError(detail, **common_kwargs)
            raise LLMResponseError(
                detail,
                status_code=status_code,
                **common_kwargs,
            )
        elif status_code >= 500:
            raise LLMResponseError(
                f"Server error: {detail}",
                status_code=status_code,
                **common_kwargs,
            )
        else:
            raise LLMResponseError(
                detail,
                status_code=status_code,
                **common_kwargs,
            )

    async def complete(
        self,
        prompt: str | list[Message],
        *,
        system_prompt: Optional[str] = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """
        Generate a complete response from the LLM.

        Args:
            prompt: The input prompt (string or list of messages)
            system_prompt: Optional system prompt to override config default
            **kwargs: Additional generation parameters

        Returns:
            LLMResponse with the generated text

        Raises:
            LLMConnectionError: If connection fails
            LLMAuthenticationError: If authentication fails
            LLMRateLimitError: If rate limited
            LLMTimeoutError: If request times out
            LLMResponseError: If response is invalid
            LLMModelNotFoundError: If model doesn't exist
            LLMContextLengthError: If input too long
        """
        client = await self._get_client()
        messages = self._prepare_messages(prompt, system_prompt)
        params = self._merge_generation_params(**kwargs)

        request_body = {
            "messages": messages,
            "stream": False,
            **params,
        }

        logger.debug(f"Sending completion request to {self.config.base_url}/chat/completions")

        try:
            response = await client.post(
                "/chat/completions",
                json=request_body,
            )

            if not response.is_success:
                self._handle_error_response(response)

            data = response.json()
            choice = data["choices"][0]

            return LLMResponse(
                content=choice["message"]["content"],
                model=data.get("model", self.config.model),
                finish_reason=choice.get("finish_reason"),
                usage=data.get("usage"),
                raw_response=data,
            )

        except httpx.TimeoutException as e:
            raise LLMTimeoutError(
                f"Request timed out after {self.config.timeout}s: {e}",
                provider=self.provider_name,
                model=self.model_name,
            )
        except httpx.ConnectError as e:
            raise LLMConnectionError(
                f"Failed to connect to {self.config.base_url}: {e}",
                provider=self.provider_name,
                model=self.model_name,
            )
        except (LLMAuthenticationError, LLMRateLimitError, LLMTimeoutError, LLMResponseError):
            raise
        except Exception as e:
            raise LLMConnectionError(
                f"Request failed: {e}",
                provider=self.provider_name,
                model=self.model_name,
            )

    async def stream(
        self,
        prompt: str | list[Message],
        *,
        system_prompt: Optional[str] = None,
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]:
        """
        Stream a response from the LLM chunk by chunk.

        Args:
            prompt: The input prompt (string or list of messages)
            system_prompt: Optional system prompt to override config default
            **kwargs: Additional generation parameters

        Yields:
            StreamChunk objects with partial response text

        Raises:
            LLMConnectionError: If connection fails
            LLMAuthenticationError: If authentication fails
            LLMRateLimitError: If rate limited
            LLMTimeoutError: If request times out
            LLMResponseError: If response is invalid
        """
        client = await self._get_client()
        messages = self._prepare_messages(prompt, system_prompt)
        params = self._merge_generation_params(**kwargs)

        request_body = {
            "messages": messages,
            "stream": True,
            **params,
        }

        logger.debug(f"Sending streaming request to {self.config.base_url}/chat/completions")

        try:
            async with client.stream(
                "POST",
                "/chat/completions",
                json=request_body,
            ) as response:
                if not response.is_success:
                    # Need to read the body for error details
                    await response.aread()
                    self._handle_error_response(response)

                async for line in response.aiter_lines():
                    if not line:
                        continue

                    # Handle SSE format
                    if line.startswith("data: "):
                        line = line[6:]  # Remove "data: " prefix

                    if line == "[DONE]":
                        break

                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        logger.warning(f"Failed to parse SSE line: {line}")
                        continue

                    # Extract content from the chunk
                    choices = data.get("choices", [])
                    if not choices:
                        continue

                    choice = choices[0]
                    delta = choice.get("delta", {})
                    content = delta.get("content", "")
                    finish_reason = choice.get("finish_reason")

                    if content or finish_reason:
                        yield StreamChunk(
                            content=content,
                            finish_reason=finish_reason,
                            is_final=finish_reason is not None,
                        )

        except httpx.TimeoutException as e:
            raise LLMTimeoutError(
                f"Stream timed out after {self.config.timeout}s: {e}",
                provider=self.provider_name,
                model=self.model_name,
            )
        except httpx.ConnectError as e:
            raise LLMConnectionError(
                f"Failed to connect to {self.config.base_url}: {e}",
                provider=self.provider_name,
                model=self.model_name,
            )
        except (LLMAuthenticationError, LLMRateLimitError, LLMTimeoutError, LLMResponseError):
            raise
        except Exception as e:
            raise LLMConnectionError(
                f"Stream failed: {e}",
                provider=self.provider_name,
                model=self.model_name,
            )

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def list_models(self) -> list[dict[str, Any]]:
        """
        List available models from the server.

        Returns:
            List of model info dicts

        Raises:
            LLMConnectionError: If the request fails
        """
        client = await self._get_client()

        try:
            response = await client.get("/models")
            if not response.is_success:
                self._handle_error_response(response)

            data = response.json()
            return data.get("data", [])

        except httpx.TimeoutException as e:
            raise LLMTimeoutError(
                f"Request timed out: {e}",
                provider=self.provider_name,
                model=self.model_name,
            )
        except httpx.ConnectError as e:
            raise LLMConnectionError(
                f"Failed to connect: {e}",
                provider=self.provider_name,
                model=self.model_name,
            )
