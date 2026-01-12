"""
Intent classification for the Tutor AI Agent.

This module handles classifying what the student wants based on their message.

Design decisions:
- No OTHER/fallback intent - unmatched intents return intent=None
- user_intent_description is ALWAYS populated by the LLM
- When intent is None, FallbackStrategy handles the response
"""

from computor_agent.tutor.intents.types import (
    Intent,
    IntentClassification,
    MESSAGING_INTENTS,
)
from computor_agent.tutor.intents.classifier import IntentClassifier

__all__ = [
    "Intent",
    "IntentClassification",
    "IntentClassifier",
    "MESSAGING_INTENTS",
]
