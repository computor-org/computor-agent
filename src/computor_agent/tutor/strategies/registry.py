"""
Strategy registry for the Tutor AI Agent.

Maps intents to their handling strategies.
"""

from typing import TYPE_CHECKING

from computor_agent.tutor.intents.types import Intent
from computor_agent.tutor.strategies.base import BaseStrategy
from computor_agent.tutor.strategies.implementations import (
    ClarificationStrategy,
    HelpDebugStrategy,
    HelpReviewStrategy,
    OtherStrategy,
    QuestionExampleStrategy,
    QuestionHowtoStrategy,
    SubmissionReviewStrategy,
)

if TYPE_CHECKING:
    from computor_agent.tutor.config import GradingConfig, PersonalityConfig


class StrategyRegistry:
    """
    Registry that maps intents to strategies.

    Usage:
        registry = StrategyRegistry(personality_config)
        strategy = registry.get(Intent.QUESTION_EXAMPLE)
        response = await strategy.execute(context, llm, config)
    """

    def __init__(
        self,
        personality_config: "PersonalityConfig",
        grading_config: "GradingConfig | None" = None,
    ) -> None:
        """
        Initialize the registry with all strategies.

        Args:
            personality_config: Personality configuration for all strategies
            grading_config: Optional grading configuration for submission strategy
        """
        self.personality_config = personality_config
        self.grading_enabled = grading_config.enabled if grading_config else False

        # Create strategy instances
        self._strategies: dict[Intent, BaseStrategy] = {
            Intent.QUESTION_EXAMPLE: QuestionExampleStrategy(personality_config),
            Intent.QUESTION_HOWTO: QuestionHowtoStrategy(personality_config),
            Intent.HELP_DEBUG: HelpDebugStrategy(personality_config),
            Intent.HELP_REVIEW: HelpReviewStrategy(personality_config),
            Intent.SUBMISSION_REVIEW: SubmissionReviewStrategy(
                personality_config,
                grading_enabled=self.grading_enabled,
            ),
            Intent.CLARIFICATION: ClarificationStrategy(personality_config),
            Intent.OTHER: OtherStrategy(personality_config),
        }

        # Fallback strategy
        self._fallback = self._strategies[Intent.OTHER]

    def get(self, intent: Intent) -> BaseStrategy:
        """
        Get the strategy for an intent.

        Args:
            intent: The intent to get strategy for

        Returns:
            The strategy for handling this intent
        """
        return self._strategies.get(intent, self._fallback)

    def register(self, intent: Intent, strategy: BaseStrategy) -> None:
        """
        Register a custom strategy for an intent.

        Args:
            intent: The intent to register for
            strategy: The strategy instance
        """
        self._strategies[intent] = strategy

    def list_strategies(self) -> list[tuple[Intent, str]]:
        """
        List all registered strategies.

        Returns:
            List of (intent, strategy_name) tuples
        """
        return [(intent, strategy.name) for intent, strategy in self._strategies.items()]

    def __contains__(self, intent: Intent) -> bool:
        """Check if an intent has a registered strategy."""
        return intent in self._strategies

    def __getitem__(self, intent: Intent) -> BaseStrategy:
        """Get strategy by intent (dict-like access)."""
        return self.get(intent)
