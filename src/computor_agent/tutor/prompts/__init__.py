"""
Prompt templates for the Tutor AI Agent.

This module provides default prompt templates that can be overridden
via configuration files for deployment customization.

Templates use Python string formatting with named placeholders:
- {tutor_name}: Name of the tutor
- {language}: Language code
- {assignment_description}: Description of the assignment
- {student_code}: Relevant student code
- {previous_messages}: Formatted previous conversation
- etc.
"""

from computor_agent.tutor.prompts.templates import (
    SECURITY_DETECTION_PROMPT,
    SECURITY_CONFIRMATION_PROMPT,
    INTENT_CLASSIFICATION_PROMPT,
    PERSONALITY_PROMPTS,
    STRATEGY_PROMPTS,
)

__all__ = [
    "SECURITY_DETECTION_PROMPT",
    "SECURITY_CONFIRMATION_PROMPT",
    "INTENT_CLASSIFICATION_PROMPT",
    "PERSONALITY_PROMPTS",
    "STRATEGY_PROMPTS",
]
