"""
Security types for the Tutor AI Agent.

Defines threat types, detection results, and security check outcomes.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class ThreatType(str, Enum):
    """Types of security threats that can be detected."""

    # Message-based threats
    PROMPT_INJECTION = "prompt_injection"
    """Attempt to manipulate the AI's behavior via prompt injection."""

    CREDENTIAL_EXTRACTION = "credential_extraction"
    """Attempt to extract credentials, API keys, or secrets."""

    SYSTEM_PROMPT_EXTRACTION = "system_prompt_extraction"
    """Attempt to reveal the system prompt or instructions."""

    ROLE_MANIPULATION = "role_manipulation"
    """Attempt to make the AI act as a different role/persona."""

    # Code-based threats
    MALICIOUS_CODE = "malicious_code"
    """Code that appears designed to harm or exploit."""

    DATA_EXFILTRATION = "data_exfiltration"
    """Code designed to steal or transmit sensitive data."""

    OBFUSCATED_PAYLOAD = "obfuscated_payload"
    """Suspicious obfuscated code that may hide malicious intent."""

    # Other
    HARASSMENT = "harassment"
    """Abusive, threatening, or harassing content."""

    ACADEMIC_DISHONESTY = "academic_dishonesty"
    """Obvious plagiarism or cheating attempt."""

    OTHER = "other"
    """Other security concern."""


class ThreatLevel(str, Enum):
    """Severity level of a detected threat."""

    NONE = "none"
    """No threat detected."""

    LOW = "low"
    """Minor concern, may be false positive."""

    MEDIUM = "medium"
    """Moderate concern, warrants attention."""

    HIGH = "high"
    """Serious threat, should be blocked."""

    CRITICAL = "critical"
    """Severe threat, must be blocked and reported."""


@dataclass
class ThreatDetection:
    """
    A single detected threat.

    Represents one potential security issue found during analysis.
    """

    threat_type: ThreatType
    """Type of threat detected."""

    level: ThreatLevel
    """Severity level."""

    description: str
    """Human-readable description of the threat."""

    evidence: Optional[str] = None
    """Specific text/code that triggered detection."""

    source: str = "unknown"
    """Source of the threat: 'message' or 'code'."""

    file_path: Optional[str] = None
    """If from code, the file path where found."""

    line_number: Optional[int] = None
    """If from code, the line number."""

    def __repr__(self) -> str:
        return f"ThreatDetection(type={self.threat_type.value}, level={self.level.value})"


@dataclass
class SecurityCheckResult:
    """
    Complete result of a security check.

    Contains all detected threats and the final decision.
    """

    is_safe: bool
    """True if content passed security check."""

    threats: list[ThreatDetection] = field(default_factory=list)
    """List of detected threats (may be empty if safe)."""

    was_confirmed: bool = False
    """True if a confirmation check was run."""

    confirmation_agreed: Optional[bool] = None
    """If confirmed, whether the confirmation agreed with detection."""

    checked_at: datetime = field(default_factory=datetime.now)
    """Timestamp of the check."""

    check_duration_ms: Optional[float] = None
    """How long the check took in milliseconds."""

    # Context for logging
    submission_group_id: Optional[str] = None
    """Submission group being checked."""

    user_id: Optional[str] = None
    """User whose content was checked."""

    message_id: Optional[str] = None
    """Message ID if checking a message."""

    @property
    def highest_threat_level(self) -> ThreatLevel:
        """Get the highest threat level among all detections."""
        if not self.threats:
            return ThreatLevel.NONE

        level_order = [
            ThreatLevel.NONE,
            ThreatLevel.LOW,
            ThreatLevel.MEDIUM,
            ThreatLevel.HIGH,
            ThreatLevel.CRITICAL,
        ]

        highest = ThreatLevel.NONE
        for threat in self.threats:
            if level_order.index(threat.level) > level_order.index(highest):
                highest = threat.level

        return highest

    @property
    def should_block(self) -> bool:
        """Whether this result warrants blocking the response."""
        return self.highest_threat_level in (ThreatLevel.HIGH, ThreatLevel.CRITICAL)

    def to_log_dict(self) -> dict:
        """Convert to dictionary for logging."""
        return {
            "is_safe": self.is_safe,
            "threat_count": len(self.threats),
            "highest_level": self.highest_threat_level.value,
            "was_confirmed": self.was_confirmed,
            "confirmation_agreed": self.confirmation_agreed,
            "checked_at": self.checked_at.isoformat(),
            "submission_group_id": self.submission_group_id,
            "user_id": self.user_id,
            "message_id": self.message_id,
            "threats": [
                {
                    "type": t.threat_type.value,
                    "level": t.level.value,
                    "description": t.description,
                    "source": t.source,
                }
                for t in self.threats
            ],
        }

    def __repr__(self) -> str:
        status = "SAFE" if self.is_safe else f"THREAT ({len(self.threats)} issues)"
        return f"SecurityCheckResult({status})"
