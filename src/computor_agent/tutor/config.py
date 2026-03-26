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
        default=True,
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

    # Enhanced context options
    include_test_results: bool = Field(
        default=True,
        description="Include parsed test results in context",
    )
    include_submission_history: bool = Field(
        default=True,
        description="Include submission history and improvement analysis",
    )
    include_reference_comparison: bool = Field(
        default=False,
        description="Include diff comparison with reference solution",
    )
    include_student_progress: bool = Field(
        default=False,
        description="Include student's overall course progress",
    )
    include_artifact_content: bool = Field(
        default=False,
        description="Include extracted artifact content (alternative to repo code)",
    )
    max_history_attempts: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Maximum number of historical submissions to analyze",
    )

    # Cache directory for downloaded content (descriptions, references)
    cache_dir: Optional[Path] = Field(
        default=None,
        description="Directory for caching downloaded content (default: /tmp/computor-agent)",
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
    clarification: StrategyConfig = Field(
        default_factory=StrategyConfig,
        description="Strategy for follow-up clarification questions",
    )
    fallback: StrategyConfig = Field(
        default_factory=StrategyConfig,
        description="Fallback strategy for unmatched intents",
    )


class TriggerTag(str):
    """
    A tag that triggers the tutor agent to respond.

    Tags in message titles follow the format: #<tag> where tag is any
    non-whitespace string. Examples: #ai, #ai-help, #review, #tutor

    The # prefix is NOT included in the tag value — it's added automatically
    when matching in titles.

    Can be used as a plain string in YAML config:
        request_tags: ["ai", "tutor"]
        response_tag: "ai-response"
    """

    def __new__(cls, value: str = ""):
        # Strip # prefix if provided, and normalize
        cleaned = value.strip().lstrip("#")
        return super().__new__(cls, cleaned)

    def __str__(self) -> str:
        return f"#{str.__str__(self)}"

    @property
    def tag(self) -> str:
        """Return the tag string without # prefix."""
        return str.__str__(self)


class TriggerConfig(BaseModel):
    """
    Configuration for message trigger detection.

    Defines which tags in message titles trigger the tutor agent to respond.
    Tags are simple strings (without #) that match #<tag> in message titles.

    If request_tags are defined, triggers are enabled automatically.
    Set enabled=False explicitly to disable triggers even with tags defined.

    Example YAML configuration:
        ```yaml
        triggers:
          request_tags:
            - "ai"
            - "tutor"
          response_tag: "ai-response"
          check_submissions: true
        ```

    Legacy scope::value format (e.g., "ai::request") still works — it's just
    a string containing "::". No special handling needed.
    """

    enabled: Optional[bool] = Field(
        default=None,
        description="Enable tag-based trigger detection. If not set, enabled when request_tags are defined.",
    )
    request_tags: list[str] = Field(
        default_factory=list,
        description="Tags that trigger the agent to respond (e.g., ['ai', 'tutor']). Without # prefix.",
    )
    response_tag: str = Field(
        default="ai-response",
        description="Tag added to agent responses (e.g., 'ai-response'). Without # prefix.",
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
        """Return list of tag strings for API queries (without # prefix)."""
        return [t.lstrip("#") for t in self.request_tags]

    @property
    def response_tag_string(self) -> str:
        """Return the response tag string (without # prefix)."""
        return self.response_tag.lstrip("#")


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

        triggers:
          request_tags:
            - "ai"
            - "tutor"
          response_tag: "ai-response"

        notes:
          enabled: true
          notes_dir: "~/.computor/notes"
          max_notes_in_context: 3

        strategies:
          question_example:
            enabled: true
            max_response_tokens: 1000
          help_review:
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
    triggers: TriggerConfig = Field(
        default_factory=TriggerConfig,
        description="Tag-based trigger detection settings",
    )
    scheduler: Optional[dict] = Field(
        default=None,
        description="Scheduler configuration (SchedulerConfig dict). Loaded separately by CLI.",
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
