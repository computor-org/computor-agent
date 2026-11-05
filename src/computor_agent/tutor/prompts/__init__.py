"""
Prompt templates for the Tutor AI Agent.

This module provides the built-in prompts. Each can be overridden by a file
in the prompts directory; VARIABLE_REFERENCE.md lists the placeholders.
"""

from computor_agent.tutor.prompts.templates import (
    SECURITY_DETECTION_PROMPT,
    SECURITY_CONFIRMATION_PROMPT,
    PERSONALITY_PROMPTS,
    TUTOR_SYSTEM_PROMPT,
)

__all__ = [
    "SECURITY_DETECTION_PROMPT",
    "SECURITY_CONFIRMATION_PROMPT",
    "PERSONALITY_PROMPTS",
    "TUTOR_SYSTEM_PROMPT",
]
