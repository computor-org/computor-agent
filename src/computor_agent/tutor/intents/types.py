"""
Intent types for the Tutor AI Agent.

Defines the possible intents that can be classified from student messages.

Design decisions:
- No OTHER/fallback intent - unmatched intents return intent=None
- user_intent_description is ALWAYS populated by the LLM
- Each intent has a description for prompt generation
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Intent(str, Enum):
    """
    Possible intents from student messages.

    Each intent maps to a specific response strategy.
    When no intent matches, intent=None and FallbackStrategy is used.
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

    # Follow-up
    CLARIFICATION = "clarification"
    """Follow-up question to a previous response."""

    # Note: No OTHER - unmatched intents return intent=None

    @property
    def description(self) -> str:
        """Human-readable description for LLM prompt."""
        descriptions = {
            Intent.QUESTION_EXAMPLE: "Questions about the assignment requirements, what to do, or expected output",
            Intent.QUESTION_HOWTO: "General programming how-to questions (syntax, library usage, concepts)",
            Intent.HELP_DEBUG: "Student has an error or bug and needs debugging assistance",
            Intent.HELP_REVIEW: "Student wants code review, feedback, or validation of their solution",
            Intent.CLARIFICATION: "Follow-up question to clarify a previous AI response",
        }
        return descriptions.get(self, "Unknown intent")


# All defined intents
MESSAGING_INTENTS = [
    Intent.QUESTION_EXAMPLE,
    Intent.QUESTION_HOWTO,
    Intent.HELP_DEBUG,
    Intent.HELP_REVIEW,
    Intent.CLARIFICATION,
]


@dataclass
class IntentClassification:
    """
    Result of intent classification.

    The LLM always provides user_intent_description (what the user wants).
    The intent field is None when no defined intent matches.
    """

    intent: Optional[Intent]
    """The classified intent, or None if no defined intent matches."""

    confidence: float
    """Confidence score (0.0 to 1.0). 0.0 if intent is None."""

    user_intent_description: str
    """ALWAYS populated - LLM's description of what the user wants."""

    reasoning: Optional[str] = None
    """Optional explanation of why this intent was chosen (or why no match)."""

    secondary_intent: Optional[Intent] = None
    """Optional secondary intent if the message could be multiple things."""

    @property
    def is_matched(self) -> bool:
        """Whether a defined intent was matched."""
        return self.intent is not None

    def __repr__(self) -> str:
        intent_str = self.intent.value if self.intent else "None"
        return (
            f"IntentClassification(intent={intent_str}, "
            f"confidence={self.confidence:.2f}, "
            f"description={self.user_intent_description[:50]}...)"
        )
