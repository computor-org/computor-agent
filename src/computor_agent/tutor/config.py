"""
Configuration for the Tutor AI Agent.

This module defines all configuration options for the tutor agent,
including personality, security settings, context options, and grading.
"""

import json
import re
from enum import Enum
from pathlib import Path
from typing import Optional, Union

import yaml
from pydantic import BaseModel, Field, field_validator


class PersonalityTone(str, Enum):
    """Predefined personality tones for the tutor."""

    FRIENDLY_PROFESSIONAL = "friendly_professional"
    STRICT = "strict"
    CASUAL = "casual"
    ENCOURAGING = "encouraging"


class PersonalityConfig(BaseModel):
    """
    Personality configuration for the tutor agent.

    Defines how the tutor presents itself and communicates.
    """

    name: str = Field(
        default="Tutor AI",
        description="Display name of the tutor",
    )
    tone: PersonalityTone = Field(
        default=PersonalityTone.FRIENDLY_PROFESSIONAL,
        description="Communication tone",
    )
    language: str = Field(
        default="en",
        description="Primary language (ISO 639-1 code)",
    )
    custom_system_prompt_prefix: Optional[str] = Field(
        default=None,
        description="Custom text prepended to all system prompts",
    )
    custom_system_prompt_suffix: Optional[str] = Field(
        default=None,
        description="Custom text appended to all system prompts",
    )


class SecurityConfig(BaseModel):
    """
    Security configuration for threat detection.

    The security gate checks both student messages and repository code
    for malicious content (prompt injection, manipulation attempts, etc.).
    """

    enabled: bool = Field(
        default=True,
        description="Enable security checks",
    )
    require_confirmation: bool = Field(
        default=True,
        description="Use 2nd LLM call to confirm detected threats",
    )
    threat_log_path: Optional[Path] = Field(
        default=None,
        description="Path to threat log file (None = use default logging)",
    )
    block_on_threat: bool = Field(
        default=True,
        description="Block response if threat confirmed (False = log only)",
    )
    check_messages: bool = Field(
        default=True,
        description="Check student messages for prompt injection",
    )
    check_code: bool = Field(
        default=True,
        description="Check student repository code for malicious content",
    )


class ContextConfig(BaseModel):
    """
    Configuration for conversation context building.

    Controls what information is gathered before processing.
    """

    include_previous_messages: int = Field(
        default=3,
        ge=0,
        le=20,
        description="Number of previous messages to include (0 = none)",
    )
    include_course_member_comments: bool = Field(
        default=True,
        description="Include tutor/lecturer notes about the student",
    )
    include_reference_solution: bool = Field(
        default=False,
        description="Include example/reference solution in context",
    )
    max_code_lines: int = Field(
        default=1000,
        ge=100,
        description="Maximum lines of code to include from repository",
    )
    max_code_files: int = Field(
        default=20,
        ge=1,
        description="Maximum number of code files to include",
    )

    # Student notes storage
    student_notes_enabled: bool = Field(
        default=False,
        description="Enable storing/reading student notes from filesystem",
    )
    student_notes_dir: Optional[Path] = Field(
        default=None,
        description="Directory for student notes (uses user UUID as filename)",
    )


class GradingConfig(BaseModel):
    """
    Configuration for automated grading.

    Controls whether and how the tutor assigns grades.
    """

    enabled: bool = Field(
        default=False,
        description="Enable automated grading for submissions",
    )
    auto_submit_grade: bool = Field(
        default=False,
        description="Automatically POST grade to API (requires enabled=True)",
    )
    default_status: int = Field(
        default=0,
        ge=0,
        le=3,
        description="Default grading status (0=NOT_REVIEWED, 1=CORRECTED, 2=CORRECTION_NECESSARY, 3=IMPROVEMENT_POSSIBLE)",
    )
    require_human_review: bool = Field(
        default=True,
        description="Flag submissions for human review after grading",
    )
    min_grade: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Minimum grade value",
    )
    max_grade: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Maximum grade value",
    )


class StrategyConfig(BaseModel):
    """
    Configuration for individual response strategies.

    Each strategy can be enabled/disabled and configured separately.
    """

    enabled: bool = Field(
        default=True,
        description="Enable this strategy",
    )
    max_response_tokens: int = Field(
        default=1000,
        ge=100,
        description="Maximum tokens in LLM response",
    )
    system_prompt_file: Optional[Path] = Field(
        default=None,
        description="Custom system prompt file (overrides default)",
    )
    temperature: float = Field(
        default=0.7,
        ge=0.0,
        le=2.0,
        description="LLM temperature for this strategy",
    )


class StrategiesConfig(BaseModel):
    """Configuration for all strategies."""

    question_example: StrategyConfig = Field(
        default_factory=StrategyConfig,
        description="Strategy for questions about the assignment",
    )
    question_howto: StrategyConfig = Field(
        default_factory=StrategyConfig,
        description="Strategy for general how-to questions",
    )
    help_debug: StrategyConfig = Field(
        default_factory=StrategyConfig,
        description="Strategy for debugging help requests",
    )
    help_review: StrategyConfig = Field(
        default_factory=StrategyConfig,
        description="Strategy for code review requests",
    )
    submission_review: StrategyConfig = Field(
        default_factory=StrategyConfig,
        description="Strategy for official submission reviews",
    )
    clarification: StrategyConfig = Field(
        default_factory=StrategyConfig,
        description="Strategy for follow-up clarification questions",
    )
    other: StrategyConfig = Field(
        default_factory=StrategyConfig,
        description="Fallback strategy for unclear intents",
    )


class TriggerTag(BaseModel):
    """
    A tag that triggers the tutor agent to respond.

    Tags in message titles follow the format: #scope::value
    Example: #ai::request, #tutor::help, #review::needed

    The agent will respond to messages containing any of the configured trigger tags.
    """

    scope: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Tag scope (e.g., 'ai', 'tutor', 'review')",
    )
    value: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Tag value (e.g., 'request', 'help', 'needed')",
    )

    @field_validator("scope", "value")
    @classmethod
    def validate_no_special_chars(cls, v: str) -> str:
        """Ensure scope and value don't contain special characters."""
        if "::" in v or "#" in v:
            raise ValueError("Tag scope/value cannot contain '::' or '#'")
        return v.strip().lower()

    @property
    def full_tag(self) -> str:
        """Return the full tag string (e.g., 'ai::request')."""
        return f"{self.scope}::{self.value}"

    def __str__(self) -> str:
        return f"#{self.full_tag}"


class TriggerConfig(BaseModel):
    """
    Configuration for message trigger detection.

    Defines which tags in message titles trigger the tutor agent to respond.
    The agent queries the backend for messages with these tags and responds
    to any unprocessed matches.

    If request_tags are defined, triggers are enabled automatically.
    Set enabled=False explicitly to disable triggers even with tags defined.

    Example YAML configuration:
        ```yaml
        triggers:
          request_tags:
            - scope: "ai"
              value: "request"
            - scope: "tutor"
              value: "help"
          response_tag:
            scope: "ai"
            value: "response"
          check_submissions: true
        ```
    """

    enabled: Optional[bool] = Field(
        default=None,
        description="Enable tag-based trigger detection. If not set, enabled when request_tags are defined.",
    )
    request_tags: list[TriggerTag] = Field(
        default_factory=list,
        description="Tags that trigger the agent to respond (message must have at least one)",
    )
    response_tag: TriggerTag = Field(
        default_factory=lambda: TriggerTag(scope="ai", value="response"),
        description="Tag added to agent responses (used to avoid duplicate responses)",
    )
    check_submissions: bool = Field(
        default=True,
        description="Also trigger on submission artifacts with submit=True",
    )
    require_all_tags: bool = Field(
        default=False,
        description="If True, message must have ALL request_tags. If False, ANY tag triggers.",
    )

    @property
    def is_enabled(self) -> bool:
        """Check if triggers are enabled. True if enabled is set, or if request_tags are defined."""
        if self.enabled is not None:
            return self.enabled
        return len(self.request_tags) > 0

    @property
    def request_tag_strings(self) -> list[str]:
        """Return list of full tag strings for API queries."""
        return [tag.full_tag for tag in self.request_tags]

    @property
    def response_tag_string(self) -> str:
        """Return the response tag string for API queries."""
        return self.response_tag.full_tag


def parse_timeout(timeout_str: str) -> int:
    """
    Parse a human-readable timeout string into seconds.

    Supported formats:
        - "30s" or "30sec" or "30 seconds" → 30 seconds
        - "5m" or "5min" or "5 minutes" → 300 seconds
        - "2h" or "2hr" or "2 hours" → 7200 seconds
        - "1d" or "1 day" or "1 days" → 86400 seconds
        - "1w" or "1 week" or "1 weeks" → 604800 seconds

    Args:
        timeout_str: Human-readable timeout string

    Returns:
        Timeout in seconds

    Raises:
        ValueError: If format is not recognized
    """
    timeout_str = timeout_str.strip().lower()

    # Pattern: number followed by unit
    match = re.match(r"^(\d+)\s*(s|sec|seconds?|m|min|minutes?|h|hr|hours?|d|days?|w|weeks?)$", timeout_str)
    if not match:
        raise ValueError(
            f"Invalid timeout format: '{timeout_str}'. "
            "Use formats like '30s', '5m', '2h', '1d', '1w'"
        )

    value = int(match.group(1))
    unit = match.group(2)

    if unit in ("s", "sec", "second", "seconds"):
        return value
    elif unit in ("m", "min", "minute", "minutes"):
        return value * 60
    elif unit in ("h", "hr", "hour", "hours"):
        return value * 3600
    elif unit in ("d", "day", "days"):
        return value * 86400
    elif unit in ("w", "week", "weeks"):
        return value * 604800
    else:
        raise ValueError(f"Unknown time unit: {unit}")


class NotesConfig(BaseModel):
    """
    Configuration for the AI's notes/memory system.

    The AI writes notes to itself after processing interactions.
    These notes are read before processing new messages to provide
    continuity and context about previous conversations.

    Example YAML configuration:
        ```yaml
        notes:
          enabled: true
          notes_dir: "~/.computor/notes"
          max_notes_in_context: 3
        ```
    """

    enabled: bool = Field(
        default=True,
        description="Enable AI note-taking (memory across sessions)",
    )
    notes_dir: Optional[Path] = Field(
        default=None,
        description="Directory to store notes (None = ~/.computor/notes)",
    )
    max_notes_in_context: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Maximum number of previous notes to include in context",
    )

    def get_notes_dir(self) -> Path:
        """Get the notes directory, with default fallback."""
        if self.notes_dir:
            return Path(self.notes_dir).expanduser().resolve()
        return Path("~/.computor/notes").expanduser().resolve()


class TutorConfig(BaseModel):
    """
    Complete configuration for the Tutor AI Agent.

    Example YAML configuration file:
        ```yaml
        personality:
          name: "Course Tutor"
          tone: "friendly_professional"
          language: "en"

        security:
          enabled: true
          require_confirmation: true
          block_on_threat: true

        context:
          include_previous_messages: 3
          include_course_member_comments: true
          student_notes_enabled: true
          student_notes_dir: "/var/lib/computor/student-notes"

        grading:
          enabled: false
          auto_submit_grade: false

        triggers:
          request_tags:
            - scope: "ai"
              value: "request"
            - scope: "tutor"
              value: "help"
          response_tag:
            scope: "ai"
            value: "response"

        notes:
          enabled: true
          notes_dir: "~/.computor/notes"
          max_notes_in_context: 3

        strategies:
          question_example:
            enabled: true
            max_response_tokens: 1000
          submission_review:
            enabled: true
            temperature: 0.5
        ```
    """

    personality: PersonalityConfig = Field(
        default_factory=PersonalityConfig,
        description="Personality and communication settings",
    )
    security: SecurityConfig = Field(
        default_factory=SecurityConfig,
        description="Security and threat detection settings",
    )
    context: ContextConfig = Field(
        default_factory=ContextConfig,
        description="Context building settings",
    )
    grading: GradingConfig = Field(
        default_factory=GradingConfig,
        description="Automated grading settings",
    )
    triggers: TriggerConfig = Field(
        default_factory=TriggerConfig,
        description="Tag-based trigger detection settings",
    )
    notes: NotesConfig = Field(
        default_factory=NotesConfig,
        description="AI note-taking (memory) settings",
    )
    strategies: StrategiesConfig = Field(
        default_factory=StrategiesConfig,
        description="Strategy-specific settings",
    )

    @classmethod
    def from_file(cls, path: Union[str, Path]) -> "TutorConfig":
        """
        Load configuration from a YAML or JSON file.

        Args:
            path: Path to configuration file

        Returns:
            TutorConfig instance

        Raises:
            FileNotFoundError: If file doesn't exist
        """
        path = Path(path).expanduser().resolve()

        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {path}")

        content = path.read_text()

        if path.suffix in (".yaml", ".yml"):
            data = yaml.safe_load(content)
        elif path.suffix == ".json":
            data = json.loads(content)
        else:
            # Try YAML first, then JSON
            try:
                data = yaml.safe_load(content)
            except Exception:
                data = json.loads(content)

        return cls.model_validate(data or {})

    @classmethod
    def from_dict(cls, data: dict) -> "TutorConfig":
        """
        Create configuration from a dictionary.

        Args:
            data: Configuration dictionary

        Returns:
            TutorConfig instance
        """
        return cls.model_validate(data)

    def to_dict(self) -> dict:
        """
        Export configuration to a dictionary.

        Returns:
            Dictionary representation
        """
        return self.model_dump(mode="json")

    def save(self, path: Union[str, Path], format: str = "yaml") -> None:
        """
        Save configuration to a file.

        Args:
            path: Output file path
            format: Output format ('yaml' or 'json')
        """
        path = Path(path).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)

        data = self.to_dict()

        if format == "yaml":
            content = yaml.dump(data, default_flow_style=False, sort_keys=False)
        else:
            content = json.dumps(data, indent=2)

        path.write_text(content)
