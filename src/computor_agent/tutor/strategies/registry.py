"""
Strategy registry for the Tutor AI Agent.

Maps intents to their handling strategies.
"""

from typing import TYPE_CHECKING, Optional

from computor_agent.tutor.intents.types import Intent, IntentClassification
from computor_agent.tutor.strategies.base import BaseStrategy
from computor_agent.tutor.strategies.implementations import (
    ClarificationStrategy,
    FallbackStrategy,
    HelpDebugStrategy,
    HelpReviewStrategy,
    QuestionExampleStrategy,
    QuestionHowtoStrategy,
)

if TYPE_CHECKING:
    from computor_agent.tutor.config import PersonalityConfig


class StrategyRegistry:
    """
    Registry that maps intents to strategies.

    When intent is None (unmatched), uses the fallback strategy.

    Usage:
        registry = StrategyRegistry(personality_config)
        strategy = registry.get_strategy(classification)
        response = await strategy.execute(context, classification, llm, config)
    """

    def __init__(
        self,
        personality_config: "PersonalityConfig",
    ) -> None:
        """
        Initialize the registry with all strategies.

        Args:
            personality_config: Personality configuration for all strategies
        """
        self.personality_config = personality_config

        # Create fallback strategy
        self._fallback_strategy = FallbackStrategy(personality_config)

        # Create strategy instances for defined intents
        self._strategies: dict[Intent, BaseStrategy] = {
            Intent.QUESTION_EXAMPLE: QuestionExampleStrategy(personality_config),
            Intent.QUESTION_HOWTO: QuestionHowtoStrategy(personality_config),
            Intent.HELP_DEBUG: HelpDebugStrategy(personality_config),
            Intent.HELP_REVIEW: HelpReviewStrategy(personality_config),
            Intent.CLARIFICATION: ClarificationStrategy(personality_config),
        }

    @property
    def fallback_strategy(self) -> BaseStrategy:
        """The fallback strategy for unmatched intents."""
        return self._fallback_strategy

    def get_strategy(self, classification: IntentClassification) -> BaseStrategy:
        """
        Get the appropriate strategy for a classification.

        When intent is None (unmatched), returns the fallback strategy.

        Args:
            classification: The intent classification result

        Returns:
            The strategy for handling this intent
        """
        if classification.intent is None:
            return self._fallback_strategy

        return self._strategies.get(classification.intent, self._fallback_strategy)

    def get(self, intent: Optional[Intent]) -> BaseStrategy:
        """
        Get the strategy for an intent.

        Args:
            intent: The intent to get strategy for (None for fallback)

        Returns:
            The strategy for handling this intent
        """
        if intent is None:
            return self._fallback_strategy
        return self._strategies.get(intent, self._fallback_strategy)

    def register(self, intent: Intent, strategy: BaseStrategy) -> None:
        """
        Register a custom strategy for an intent.

        Args:
            intent: The intent to register for
            strategy: The strategy instance
        """
        self._strategies[intent] = strategy

    def set_fallback_strategy(self, strategy: BaseStrategy) -> None:
        """
        Set a custom fallback strategy.

        Args:
            strategy: The strategy to use for unmatched intents
        """
        self._fallback_strategy = strategy

    def list_strategies(self) -> list[tuple[Optional[Intent], str]]:
        """
        List all registered strategies.

        Returns:
            List of (intent, strategy_name) tuples
        """
        strategies = [(intent, strategy.name) for intent, strategy in self._strategies.items()]
        strategies.append((None, self._fallback_strategy.name))
        return strategies

    def __contains__(self, intent: Optional[Intent]) -> bool:
        """Check if an intent has a registered strategy."""
        if intent is None:
            return True  # Fallback always exists
        return intent in self._strategies

    def __getitem__(self, intent: Optional[Intent]) -> BaseStrategy:
        """Get strategy by intent (dict-like access)."""
        return self.get(intent)
