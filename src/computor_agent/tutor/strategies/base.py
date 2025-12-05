"""
Base strategy class for the Tutor AI Agent.

All response strategies inherit from BaseStrategy.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from computor_agent.tutor.context import ConversationContext
    from computor_agent.tutor.config import StrategyConfig
    from computor_agent.llm import LLMProvider


@dataclass
class StrategyResponse:
    """
    Response from a strategy execution.

    Contains the message to send and optional grading information.
    """

    message_content: str
    """The response message content to send to the student."""

    message_title: Optional[str] = None
    """Optional title for the message."""

    # Grading (for submission reviews)
    grade: Optional[float] = None
    """Grade value (0.0 to 1.0) if grading is enabled."""

    grade_status: Optional[int] = None
    """Grading status (0-3) if grading is enabled."""

    grade_comment: Optional[str] = None
    """Comment to attach to the grade."""

    # Metadata
    tokens_used: int = 0
    """Number of tokens used in LLM call."""

    strategy_name: str = "unknown"
    """Name of the strategy that generated this response."""

    additional_data: dict = field(default_factory=dict)
    """Any additional data from the strategy."""

    def __repr__(self) -> str:
        preview = self.message_content[:50] + "..." if len(self.message_content) > 50 else self.message_content
        return f"StrategyResponse(strategy={self.strategy_name}, content={preview!r})"


class BaseStrategy(ABC):
    """
    Base class for all response strategies.

    Each strategy handles a specific intent type (e.g., QUESTION_EXAMPLE,
    HELP_DEBUG, SUBMISSION_REVIEW) and defines how to:
    1. Build the system prompt
    2. Prepare the user message with context
    3. Process the LLM response

    Subclasses must implement:
    - name: Strategy identifier
    - build_system_prompt(): Create the system prompt
    - build_user_message(): Create the user message with context
    - execute(): Run the strategy and return response

    Example:
        ```python
        class QuestionExampleStrategy(BaseStrategy):
            name = "question_example"

            async def execute(self, context, llm, config):
                system_prompt = self.build_system_prompt(context, config)
                user_message = self.build_user_message(context)

                response = await llm.complete(
                    messages=[
                        Message(role=MessageRole.SYSTEM, content=system_prompt),
                        Message(role=MessageRole.USER, content=user_message),
                    ],
                    max_tokens=config.max_response_tokens,
                )

                return StrategyResponse(
                    message_content=response.content,
                    strategy_name=self.name,
                )
        ```
    """

    name: str = "base"
    """Identifier for this strategy."""

    @abstractmethod
    def build_system_prompt(
        self,
        context: "ConversationContext",
        config: "StrategyConfig",
    ) -> str:
        """
        Build the system prompt for this strategy.

        Args:
            context: The conversation context with all relevant data
            config: Strategy-specific configuration

        Returns:
            System prompt string
        """
        pass

    @abstractmethod
    def build_user_message(
        self,
        context: "ConversationContext",
    ) -> str:
        """
        Build the user message including relevant context.

        Args:
            context: The conversation context

        Returns:
            User message string
        """
        pass

    @abstractmethod
    async def execute(
        self,
        context: "ConversationContext",
        llm: "LLMProvider",
        config: "StrategyConfig",
    ) -> StrategyResponse:
        """
        Execute the strategy and generate a response.

        Args:
            context: The conversation context
            llm: LLM provider for generating responses
            config: Strategy-specific configuration

        Returns:
            StrategyResponse with the message to send
        """
        pass
