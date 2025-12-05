"""
Conversation context for the Tutor AI Agent.

The context is created fresh for each interaction and contains all
relevant information needed to process a student's request.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class TriggerType(str, Enum):
    """Type of trigger that initiated this context."""

    MESSAGE = "message"
    """Triggered by a new student message."""

    SUBMISSION = "submission"
    """Triggered by a new submission artifact with submit=True."""


@dataclass
class MessageInfo:
    """Information about a message."""

    id: str
    title: str
    content: str
    author_id: str
    author_name: Optional[str] = None
    is_from_student: bool = True
    created_at: Optional[datetime] = None


@dataclass
class SubmissionInfo:
    """Information about a submission artifact."""

    artifact_id: str
    submission_group_id: str
    uploaded_by_course_member_id: Optional[str] = None
    version_identifier: Optional[str] = None
    file_size: int = 0
    uploaded_at: Optional[datetime] = None


@dataclass
class StudentInfo:
    """Information about the student(s) in the submission group."""

    user_ids: list[str] = field(default_factory=list)
    """User IDs of all members in the submission group."""

    names: list[str] = field(default_factory=list)
    """Display names of all members."""

    emails: list[str] = field(default_factory=list)
    """Email addresses of all members."""

    course_member_ids: list[str] = field(default_factory=list)
    """Course member IDs of all members."""


@dataclass
class AssignmentInfo:
    """Information about the assignment/example."""

    course_content_id: str
    title: Optional[str] = None
    description: Optional[str] = None
    course_id: Optional[str] = None
    course_title: Optional[str] = None


@dataclass
class CodeContext:
    """Code from the student's repository."""

    files: dict[str, str] = field(default_factory=dict)
    """Mapping of file path -> file content."""

    total_lines: int = 0
    """Total lines of code across all files."""

    repository_path: Optional[Path] = None
    """Local path to the cloned repository."""

    truncated: bool = False
    """Whether code was truncated due to limits."""


@dataclass
class ConversationContext:
    """
    Complete context for a single interaction.

    Created fresh for each trigger (message or submission),
    used throughout processing, then discarded.

    Contains:
    - Trigger information (the message or submission)
    - Student information
    - Assignment details
    - Previous messages
    - Course member comments (tutor/lecturer notes)
    - Student notes from filesystem
    - Student's code
    - Reference solution (optional)
    """

    # Trigger
    trigger_type: TriggerType
    """What triggered this context (message or submission)."""

    submission_group_id: str
    """The submission group being processed."""

    # Trigger details
    trigger_message: Optional[MessageInfo] = None
    """The message that triggered this (if MESSAGE trigger)."""

    trigger_submission: Optional[SubmissionInfo] = None
    """The submission that triggered this (if SUBMISSION trigger)."""

    # Student info
    student: StudentInfo = field(default_factory=StudentInfo)
    """Information about the student(s)."""

    # Assignment
    assignment: Optional[AssignmentInfo] = None
    """Information about the assignment."""

    # Conversation history
    previous_messages: list[MessageInfo] = field(default_factory=list)
    """Previous messages in the conversation (most recent last)."""

    # Tutor/lecturer notes
    course_member_comments: list[str] = field(default_factory=list)
    """Comments from tutors/lecturers about this student."""

    # Student notes from filesystem
    student_notes: Optional[str] = None
    """Notes stored locally about this student (from filesystem)."""

    # Code
    student_code: Optional[CodeContext] = None
    """Code from the student's repository."""

    reference_code: Optional[CodeContext] = None
    """Reference solution code (if enabled)."""

    # Metadata
    created_at: datetime = field(default_factory=datetime.now)
    """When this context was created."""

    context_id: Optional[str] = None
    """Unique ID for this context (for logging)."""

    # Additional data
    extra: dict[str, Any] = field(default_factory=dict)
    """Any additional data needed by strategies."""

    @property
    def primary_user_id(self) -> Optional[str]:
        """Get the primary user ID (first in list)."""
        return self.student.user_ids[0] if self.student.user_ids else None

    @property
    def student_message(self) -> Optional[str]:
        """Get the trigger message content."""
        return self.trigger_message.content if self.trigger_message else None

    @property
    def has_code(self) -> bool:
        """Check if student code is available."""
        return self.student_code is not None and bool(self.student_code.files)

    @property
    def has_reference(self) -> bool:
        """Check if reference code is available."""
        return self.reference_code is not None and bool(self.reference_code.files)

    def get_formatted_previous_messages(self, max_messages: int = 3) -> str:
        """
        Format previous messages for inclusion in prompts.

        Args:
            max_messages: Maximum number of messages to include

        Returns:
            Formatted string of previous messages
        """
        if not self.previous_messages:
            return "(No previous messages)"

        messages = self.previous_messages[-max_messages:]
        formatted = []

        for msg in messages:
            role = "Student" if msg.is_from_student else "Tutor"
            formatted.append(f"[{role}]: {msg.content}")

        return "\n\n".join(formatted)

    def get_formatted_code(self, max_lines: int = 1000) -> str:
        """
        Format student code for inclusion in prompts.

        Args:
            max_lines: Maximum lines to include

        Returns:
            Formatted string of code files
        """
        if not self.has_code:
            return "(No code available)"

        formatted = []
        lines_remaining = max_lines

        for file_path, content in self.student_code.files.items():
            if lines_remaining <= 0:
                formatted.append(f"\n... (truncated, {len(self.student_code.files) - len(formatted)} more files)")
                break

            lines = content.split("\n")
            if len(lines) > lines_remaining:
                lines = lines[:lines_remaining]
                content = "\n".join(lines) + "\n... (truncated)"

            formatted.append(f"=== {file_path} ===\n{content}")
            lines_remaining -= len(lines)

        return "\n\n".join(formatted)

    def get_student_notes_path(self, notes_dir: Path) -> Path:
        """
        Get the path to the student notes file.

        Uses the primary user ID as the filename.

        Args:
            notes_dir: Directory where notes are stored

        Returns:
            Path to the notes file
        """
        user_id = self.primary_user_id or "unknown"
        return notes_dir / f"{user_id}.txt"

    def destroy(self) -> None:
        """
        Clean up the context.

        Called after processing is complete.
        Clears sensitive data from memory.
        """
        self.previous_messages.clear()
        self.course_member_comments.clear()
        self.student_notes = None

        if self.student_code:
            self.student_code.files.clear()

        if self.reference_code:
            self.reference_code.files.clear()

        self.extra.clear()

    def __repr__(self) -> str:
        return (
            f"ConversationContext("
            f"trigger={self.trigger_type.value}, "
            f"group={self.submission_group_id}, "
            f"messages={len(self.previous_messages)})"
        )
