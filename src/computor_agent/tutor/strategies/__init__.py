"""
Response strategies for the Tutor AI Agent.

Each intent maps to a strategy that:
1. Gathers required context
2. Builds the system prompt
3. Calls the LLM
4. Formats the response

Strategies are registered in a registry that maps Intent -> Strategy.
"""

from computor_agent.tutor.strategies.base import BaseStrategy, StrategyResponse
from computor_agent.tutor.strategies.implementations import (
    ClarificationStrategy,
    HelpDebugStrategy,
    HelpReviewStrategy,
    OtherStrategy,
    QuestionExampleStrategy,
    QuestionHowtoStrategy,
    SubmissionReviewStrategy,
)
from computor_agent.tutor.strategies.registry import StrategyRegistry

__all__ = [
    "BaseStrategy",
    "StrategyResponse",
    "StrategyRegistry",
    "QuestionExampleStrategy",
    "QuestionHowtoStrategy",
    "HelpDebugStrategy",
    "HelpReviewStrategy",
    "SubmissionReviewStrategy",
    "ClarificationStrategy",
    "OtherStrategy",
]
