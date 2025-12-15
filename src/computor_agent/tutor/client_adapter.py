"""
LLM Adapter for the Tutor AI Agent.

Wraps the LLM provider to provide the interface expected by TutorAgent.

Note: Client adapters have been removed. Use ComputorClient directly
from computor-client package instead.
"""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class TutorLLMAdapter:
    """
    Adapts LLM provider to the interface expected by TutorAgent.

    The TutorAgent expects:
    - complete(prompt, system_prompt=...) -> str

    But LLMProvider has:
    - complete(prompt, system_prompt=...) -> LLMResponse

    This adapter extracts the content string from the response.
    """

    def __init__(self, llm_provider: Any) -> None:
        """
        Initialize the adapter.

        Args:
            llm_provider: LLMProvider instance
        """
        self._llm = llm_provider

    async def complete(
        self,
        prompt: str,
        *,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: float = 0.7,
    ) -> str:
        """Generate a completion and return just the content string."""
        response = await self._llm.complete(
            prompt,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        # Extract content from LLMResponse
        return response.content if hasattr(response, "content") else str(response)

    async def close(self) -> None:
        """Close the underlying LLM provider."""
        if hasattr(self._llm, "close"):
            await self._llm.close()
