"""
Intent types for the Tutor AI Agent.

Defines the possible intents that can be classified from student messages.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Intent(str, Enum):
    """
    Possible intents from student messages.

    Each intent maps to a specific response strategy.
    """

    # Questions
    QUESTION_EXAMPLE = "question_example"
    """Questions about the assignment/example itself (what to do, requirements)."""

    QUESTION_HOWTO = "question_howto"
    """General how-to questions (how do I use X, what is the syntax for Y)."""

    # Help requests
    HELP_DEBUG = "help_debug"
    """Student has an error/bug and needs help finding it."""

    HELP_REVIEW = "help_review"
    """Student wants general code review/feedback."""

    # Submissions
    SUBMISSION_REVIEW = "submission_review"
    """Automatic review of official submission (submit=True artifact)."""

    # Follow-up
    CLARIFICATION = "clarification"
    """Follow-up question to a previous response."""

    # Fallback
    OTHER = "other"
    """Unclear or off-topic intent."""


@dataclass
class IntentClassification:
    """
    Result of intent classification.

    Contains the detected intent and confidence information.
    """

    intent: Intent
    """The classified intent."""

    confidence: float
    """Confidence score (0.0 to 1.0)."""

    reasoning: Optional[str] = None
    """Optional explanation of why this intent was chosen."""

    secondary_intent: Optional[Intent] = None
    """Optional secondary intent if the message could be multiple things."""

    def __repr__(self) -> str:
        return f"IntentClassification(intent={self.intent.value}, confidence={self.confidence:.2f})"
