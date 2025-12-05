"""
Security gate for the Tutor AI Agent.

This module provides threat detection for:
- Student messages (prompt injection, manipulation)
- Student repository code (malicious payloads, obfuscated threats)

The security gate uses a two-phase approach:
1. Detection: LLM analyzes content for threats
2. Confirmation: If suspicious, a second LLM call confirms

This reduces false positives while catching real threats.
"""

from computor_agent.tutor.security.types import (
    ThreatType,
    ThreatLevel,
    ThreatDetection,
    SecurityCheckResult,
)
from computor_agent.tutor.security.gate import SecurityGate

__all__ = [
    "ThreatType",
    "ThreatLevel",
    "ThreatDetection",
    "SecurityCheckResult",
    "SecurityGate",
]
