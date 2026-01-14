"""
Data models for the grading module.
"""

from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import Optional

from computor_agent.tutor.assignment_loader import AssignmentFile


class GradingStatus(IntEnum):
    """
    Grading status values matching the backend API.

    These statuses indicate the overall assessment of the submission:
    - NOT_REVIEWED: Not yet reviewed (initial state)
    - CORRECTED: Submission is correct as-is, no changes needed
    - CORRECTION_NECESSARY: Submission has significant issues that must be fixed
    - IMPROVEMENT_POSSIBLE: Submission works but could be significantly improved
    """

    NOT_REVIEWED = 0
    CORRECTED = 1
    CORRECTION_NECESSARY = 2
    IMPROVEMENT_POSSIBLE = 3

    @classmethod
    def from_string(cls, value: str) -> "GradingStatus":
        """Convert a string to GradingStatus."""
        mapping = {
            "not_reviewed": cls.NOT_REVIEWED,
            "corrected": cls.CORRECTED,
            "correction_necessary": cls.CORRECTION_NECESSARY,
            "improvement_possible": cls.IMPROVEMENT_POSSIBLE,
        }
        return mapping.get(value.lower(), cls.NOT_REVIEWED)

    def to_display_string(self) -> str:
        """Get a human-readable display string."""
        display = {
            self.NOT_REVIEWED: "Not Reviewed",
            self.CORRECTED: "Corrected",
            self.CORRECTION_NECESSARY: "Correction Necessary",
            self.IMPROVEMENT_POSSIBLE: "Improvement Possible",
        }
        return display.get(self, "Unknown")


@dataclass
class GradingResult:
    """
    Result of grading a student submission.

    Attributes:
        grade: Float between 0.0 and 1.0 (where 1.0 = 100%)
        status: The grading status (corrected, correction_necessary, improvement_possible)
        feedback: Detailed feedback for the student
        summary: Short summary of the grading (1-2 sentences)
        issues: List of specific issues found (if any)
        suggestions: List of improvement suggestions (if any)
    """

    grade: float
    status: GradingStatus
    feedback: str
    summary: str = ""
    issues: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)

    def __post_init__(self):
        """Validate grade is in valid range."""
        if not 0.0 <= self.grade <= 1.0:
            raise ValueError(f"Grade must be between 0.0 and 1.0, got {self.grade}")

    @property
    def grade_percentage(self) -> int:
        """Get the grade as a percentage (0-100)."""
        return int(round(self.grade * 100))

    def to_api_dict(self) -> dict:
        """Convert to dict format for the API (TutorGradeCreate)."""
        return {
            "grade": self.grade,
            "status": self.status.value,
            "feedback": self.feedback,
        }


@dataclass
class StudentSubmission:
    """
    A student's submission files.

    Attributes:
        files: List of submission files
        submission_path: Path to the submission directory (if local)
    """

    files: list[AssignmentFile] = field(default_factory=list)
    submission_path: Optional[Path] = None

    def get_file(self, path: str) -> Optional[AssignmentFile]:
        """Get a specific file by path."""
        for f in self.files:
            if f.path == path:
                return f
        return None

    def get_all_code(self) -> str:
        """Get all code files concatenated."""
        parts = []
        for f in self.files:
            ext = Path(f.path).suffix.lower()
            if ext in (".py", ".js", ".ts", ".java", ".c", ".cpp", ".h", ".hpp"):
                parts.append(f"# File: {f.path}\n{f.content}")
        return "\n\n".join(parts)

    def to_context_string(self) -> str:
        """Format as a context string for the LLM."""
        parts = ["## Student Submission Files"]

        for f in self.files:
            ext = Path(f.path).suffix.lower()
            lang = {
                ".py": "python",
                ".js": "javascript",
                ".ts": "typescript",
                ".java": "java",
                ".c": "c",
                ".cpp": "cpp",
                ".h": "c",
                ".hpp": "cpp",
            }.get(ext, "")

            parts.append(f"\n### {f.path}")
            parts.append(f"```{lang}\n{f.content}\n```")

        return "\n".join(parts)


@dataclass
class GradingContext:
    """
    Full context for grading a submission.

    Attributes:
        assignment_title: Title of the assignment
        assignment_description: Full description/README of the assignment
        reference_solution: Reference solution files (the correct implementation)
        student_submission: Student's submitted files
        language: Language code (e.g., 'en', 'de')
    """

    assignment_title: str
    assignment_description: str
    reference_solution: list[AssignmentFile]
    student_submission: StudentSubmission
    language: str = "en"

    def get_reference_code(self) -> str:
        """Get reference solution code concatenated."""
        parts = []
        for f in self.reference_solution:
            ext = Path(f.path).suffix.lower()
            if ext in (".py", ".js", ".ts", ".java", ".c", ".cpp", ".h", ".hpp"):
                parts.append(f"# File: {f.path}\n{f.content}")
        return "\n\n".join(parts)

    def to_prompt_context(self) -> str:
        """
        Format the full context for the grading prompt.

        Returns a structured string with all information needed for grading.
        """
        parts = [
            f"# Assignment: {self.assignment_title}",
            "",
            "## Assignment Description",
            self.assignment_description,
            "",
            "## Reference Solution",
        ]

        for f in self.reference_solution:
            ext = Path(f.path).suffix.lower()
            lang = {
                ".py": "python",
                ".js": "javascript",
                ".ts": "typescript",
                ".java": "java",
                ".c": "c",
                ".cpp": "cpp",
            }.get(ext, "")

            parts.append(f"\n### {f.path}")
            parts.append(f"```{lang}\n{f.content}\n```")

        parts.append("")
        parts.append(self.student_submission.to_context_string())

        return "\n".join(parts)
