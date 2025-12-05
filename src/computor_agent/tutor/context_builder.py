"""
Context builder for the Tutor AI Agent.

Builds ConversationContext from API data, gathering all required
information before processing a student interaction.
"""

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Protocol

from computor_agent.tutor.context import (
    AssignmentInfo,
    CodeContext,
    ConversationContext,
    MessageInfo,
    StudentInfo,
    SubmissionInfo,
    TriggerType,
)

if TYPE_CHECKING:
    from computor_agent.tutor.config import ContextConfig

logger = logging.getLogger(__name__)


class ComputorClientProtocol(Protocol):
    """Protocol for the Computor API client."""

    async def get_submission_group(self, submission_group_id: str) -> dict:
        """Get submission group details."""
        ...

    async def get_messages(self, submission_group_id: str) -> list[dict]:
        """Get messages for a submission group."""
        ...

    async def get_course_member_comments(self, course_member_id: str) -> list[dict]:
        """Get comments for a course member."""
        ...

    async def get_course_content(self, course_content_id: str) -> dict:
        """Get course content (assignment) details."""
        ...

    async def get_course_members(self, submission_group_id: str) -> list[dict]:
        """Get course members for a submission group."""
        ...


class ContextBuilder:
    """
    Builds ConversationContext from API data.

    Gathers:
    - Student information from submission group
    - Previous messages
    - Course member comments (tutor/lecturer notes)
    - Student notes from filesystem
    - Student code from repository
    - Reference code (if enabled)
    - Assignment information

    Usage:
        builder = ContextBuilder(client, config)
        context = await builder.build_for_message(
            submission_group_id="...",
            message_id="...",
        )
        # Use context, then destroy
        context.destroy()
    """

    def __init__(
        self,
        client: ComputorClientProtocol,
        config: "ContextConfig",
    ) -> None:
        """
        Initialize the context builder.

        Args:
            client: Computor API client
            config: Context configuration
        """
        self.client = client
        self.config = config

    async def build_for_message(
        self,
        submission_group_id: str,
        message: dict,
        repository_path: Optional[Path] = None,
        reference_path: Optional[Path] = None,
    ) -> ConversationContext:
        """
        Build context for a message trigger.

        Args:
            submission_group_id: The submission group ID
            message: The message dict that triggered this
            repository_path: Path to student's cloned repository
            reference_path: Path to reference solution (if enabled)

        Returns:
            ConversationContext ready for processing
        """
        # Create trigger message info
        trigger_message = MessageInfo(
            id=message.get("id", ""),
            title=message.get("title", ""),
            content=message.get("content", ""),
            author_id=message.get("author_id", ""),
            author_name=message.get("author_name"),
            is_from_student=message.get("is_from_student", True),
        )

        return await self._build_context(
            submission_group_id=submission_group_id,
            trigger_type=TriggerType.MESSAGE,
            trigger_message=trigger_message,
            trigger_submission=None,
            repository_path=repository_path,
            reference_path=reference_path,
        )

    async def build_for_submission(
        self,
        submission_group_id: str,
        artifact: dict,
        repository_path: Optional[Path] = None,
        reference_path: Optional[Path] = None,
    ) -> ConversationContext:
        """
        Build context for a submission trigger.

        Args:
            submission_group_id: The submission group ID
            artifact: The submission artifact dict that triggered this
            repository_path: Path to student's cloned repository
            reference_path: Path to reference solution (if enabled)

        Returns:
            ConversationContext ready for processing
        """
        # Create trigger submission info
        trigger_submission = SubmissionInfo(
            artifact_id=artifact.get("id", ""),
            submission_group_id=submission_group_id,
            uploaded_by_course_member_id=artifact.get("uploaded_by_course_member_id"),
            version_identifier=artifact.get("version_identifier"),
            file_size=artifact.get("file_size", 0),
        )

        return await self._build_context(
            submission_group_id=submission_group_id,
            trigger_type=TriggerType.SUBMISSION,
            trigger_message=None,
            trigger_submission=trigger_submission,
            repository_path=repository_path,
            reference_path=reference_path,
        )

    async def _build_context(
        self,
        submission_group_id: str,
        trigger_type: TriggerType,
        trigger_message: Optional[MessageInfo],
        trigger_submission: Optional[SubmissionInfo],
        repository_path: Optional[Path],
        reference_path: Optional[Path],
    ) -> ConversationContext:
        """Build the full context with all gathered data."""
        # Gather data in parallel where possible
        student_info = await self._get_student_info(submission_group_id)
        previous_messages = await self._get_previous_messages(submission_group_id)
        assignment_info = await self._get_assignment_info(submission_group_id)

        # Get course member comments if enabled
        course_member_comments: list[str] = []
        if self.config.include_course_member_comments and student_info.course_member_ids:
            for cm_id in student_info.course_member_ids:
                comments = await self._get_course_member_comments(cm_id)
                course_member_comments.extend(comments)

        # Load student notes if enabled
        student_notes: Optional[str] = None
        if self.config.student_notes_enabled and self.config.student_notes_dir:
            student_notes = self._load_student_notes(student_info.user_ids)

        # Load code if repository path provided
        student_code: Optional[CodeContext] = None
        if repository_path and repository_path.exists():
            student_code = self._load_code_from_path(
                repository_path,
                max_lines=self.config.max_code_lines,
                max_files=self.config.max_code_files,
            )

        # Load reference code if enabled and path provided
        reference_code: Optional[CodeContext] = None
        if self.config.include_reference_solution and reference_path and reference_path.exists():
            reference_code = self._load_code_from_path(
                reference_path,
                max_lines=self.config.max_code_lines,
                max_files=self.config.max_code_files,
            )

        return ConversationContext(
            trigger_type=trigger_type,
            submission_group_id=submission_group_id,
            trigger_message=trigger_message,
            trigger_submission=trigger_submission,
            student=student_info,
            assignment=assignment_info,
            previous_messages=previous_messages[: self.config.include_previous_messages],
            course_member_comments=course_member_comments,
            student_notes=student_notes,
            student_code=student_code,
            reference_code=reference_code,
        )

    async def _get_student_info(self, submission_group_id: str) -> StudentInfo:
        """Get student information from submission group."""
        try:
            members = await self.client.get_course_members(submission_group_id)

            user_ids = []
            names = []
            emails = []
            course_member_ids = []

            for member in members:
                if member.get("user_id"):
                    user_ids.append(member["user_id"])
                if member.get("display_name"):
                    names.append(member["display_name"])
                if member.get("email"):
                    emails.append(member["email"])
                if member.get("id"):
                    course_member_ids.append(member["id"])

            return StudentInfo(
                user_ids=user_ids,
                names=names,
                emails=emails,
                course_member_ids=course_member_ids,
            )
        except Exception as e:
            logger.warning(f"Failed to get student info: {e}")
            return StudentInfo()

    async def _get_previous_messages(
        self,
        submission_group_id: str,
    ) -> list[MessageInfo]:
        """Get previous messages for the submission group."""
        try:
            messages = await self.client.get_messages(submission_group_id)

            result = []
            for msg in messages:
                result.append(
                    MessageInfo(
                        id=msg.get("id", ""),
                        title=msg.get("title", ""),
                        content=msg.get("content", ""),
                        author_id=msg.get("author_id", ""),
                        author_name=msg.get("author_name"),
                        is_from_student=msg.get("is_from_student", True),
                    )
                )

            # Sort by created_at, most recent last
            # Note: Actual sorting depends on API response format
            return result
        except Exception as e:
            logger.warning(f"Failed to get previous messages: {e}")
            return []

    async def _get_assignment_info(
        self,
        submission_group_id: str,
    ) -> Optional[AssignmentInfo]:
        """Get assignment information from submission group."""
        try:
            sg = await self.client.get_submission_group(submission_group_id)
            course_content_id = sg.get("course_content_id")

            if not course_content_id:
                return None

            content = await self.client.get_course_content(course_content_id)

            return AssignmentInfo(
                course_content_id=course_content_id,
                title=content.get("title"),
                description=content.get("description"),
                course_id=content.get("course_id"),
                course_title=content.get("course_title"),
            )
        except Exception as e:
            logger.warning(f"Failed to get assignment info: {e}")
            return None

    async def _get_course_member_comments(
        self,
        course_member_id: str,
    ) -> list[str]:
        """Get comments for a course member."""
        try:
            comments = await self.client.get_course_member_comments(course_member_id)
            return [c.get("content", "") for c in comments if c.get("content")]
        except Exception as e:
            logger.warning(f"Failed to get course member comments: {e}")
            return []

    def _load_student_notes(self, user_ids: list[str]) -> Optional[str]:
        """Load student notes from filesystem."""
        if not self.config.student_notes_dir or not user_ids:
            return None

        notes_dir = Path(self.config.student_notes_dir)
        if not notes_dir.exists():
            return None

        # Try each user ID (for group submissions)
        for user_id in user_ids:
            notes_path = notes_dir / f"{user_id}.txt"
            if notes_path.exists():
                try:
                    return notes_path.read_text()
                except Exception as e:
                    logger.warning(f"Failed to read student notes: {e}")

        return None

    def _load_code_from_path(
        self,
        repo_path: Path,
        max_lines: int = 1000,
        max_files: int = 20,
    ) -> CodeContext:
        """
        Load code files from a repository path.

        Args:
            repo_path: Path to the repository
            max_lines: Maximum total lines to include
            max_files: Maximum number of files to include

        Returns:
            CodeContext with loaded files
        """
        files: dict[str, str] = {}
        total_lines = 0
        truncated = False

        # Code file extensions to include
        code_extensions = {
            ".py",
            ".java",
            ".js",
            ".ts",
            ".jsx",
            ".tsx",
            ".c",
            ".cpp",
            ".h",
            ".hpp",
            ".cs",
            ".go",
            ".rs",
            ".rb",
            ".php",
            ".swift",
            ".kt",
            ".scala",
            ".sh",
            ".sql",
            ".html",
            ".css",
            ".scss",
            ".yaml",
            ".yml",
            ".json",
            ".xml",
            ".md",
            ".txt",
        }

        # Directories to skip
        skip_dirs = {
            ".git",
            "node_modules",
            "__pycache__",
            ".venv",
            "venv",
            ".idea",
            ".vscode",
            "dist",
            "build",
            "target",
        }

        try:
            for file_path in sorted(repo_path.rglob("*")):
                if len(files) >= max_files:
                    truncated = True
                    break

                if total_lines >= max_lines:
                    truncated = True
                    break

                # Skip directories in skip list
                if any(skip in file_path.parts for skip in skip_dirs):
                    continue

                # Only include code files
                if file_path.is_file() and file_path.suffix.lower() in code_extensions:
                    try:
                        content = file_path.read_text(errors="replace")
                        lines = content.count("\n") + 1

                        # Check if adding this file would exceed limit
                        if total_lines + lines > max_lines:
                            # Truncate the content
                            remaining_lines = max_lines - total_lines
                            content = "\n".join(content.split("\n")[:remaining_lines])
                            truncated = True

                        relative_path = file_path.relative_to(repo_path)
                        files[str(relative_path)] = content
                        total_lines += lines

                    except Exception as e:
                        logger.debug(f"Failed to read file {file_path}: {e}")

        except Exception as e:
            logger.warning(f"Failed to load code from {repo_path}: {e}")

        return CodeContext(
            files=files,
            total_lines=total_lines,
            repository_path=repo_path,
            truncated=truncated,
        )

    def save_student_notes(
        self,
        user_id: str,
        notes: str,
    ) -> bool:
        """
        Save student notes to filesystem.

        Args:
            user_id: The user UUID to save notes for
            notes: The notes content

        Returns:
            True if saved successfully
        """
        if not self.config.student_notes_enabled or not self.config.student_notes_dir:
            return False

        try:
            notes_dir = Path(self.config.student_notes_dir)
            notes_dir.mkdir(parents=True, exist_ok=True)

            notes_path = notes_dir / f"{user_id}.txt"
            notes_path.write_text(notes)
            return True
        except Exception as e:
            logger.error(f"Failed to save student notes: {e}")
            return False
