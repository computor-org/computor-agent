"""
Shared JSON extraction utilities for LLM response parsing.

LLMs often return JSON wrapped in markdown code blocks, with control
characters, single quotes, or unquoted keys. This module provides
a robust extraction function used by the classifier, security gate,
and grader.
"""

import json
import re


def extract_json(text: str) -> str:
    """
    Extract a JSON object from text that may contain other content.

    Handles common LLM quirks:
    - JSON wrapped in ```json code blocks
    - Control characters in strings
    - Single quotes instead of double quotes
    - Unquoted keys

    Args:
        text: Raw text containing JSON

    Returns:
        Extracted (and possibly sanitized) JSON string

    Raises:
        ValueError: If no JSON object found
    """
    # Try to find JSON in code block first
    code_block_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if code_block_match:
        return code_block_match.group(1)

    # Find the first { and last }
    start = text.find("{")
    end = text.rfind("}") + 1

    if start == -1 or end == 0:
        raise ValueError("No JSON object found in response")

    json_str = text[start:end]

    # Sanitize control characters that small LLMs sometimes produce
    json_str = re.sub(r"[\x00-\x1f\x7f]", lambda m: f"\\u{ord(m.group()):04x}", json_str)

    # Try parsing as-is first
    try:
        json.loads(json_str)
        return json_str
    except json.JSONDecodeError:
        pass

    # Try fixing common LLM JSON issues:
    # 1. Single quotes -> double quotes
    fixed = re.sub(r"'([^']*)'(\s*[:\],}])", r'"\1"\2', json_str)
    fixed = re.sub(r"(\{|\[|,)\s*'([^']*)'", r'\1"\2"', fixed)
    # 2. Unquoted keys
    fixed = re.sub(r"([{,])\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:", r'\1"\2":', fixed)
    return fixed
