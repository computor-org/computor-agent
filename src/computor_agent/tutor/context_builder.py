"""
Context builder for the Tutor AI Agent.

Builds ConversationContext from API data, gathering all required
information before processing a student interaction.

Uses ComputorClient from computor-client package directly.
"""

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from computor_agent.tutor.context import (
    AssignmentInfo,
    CodeContext,
    ConversationContext,
    MessageInfo,
    StudentInfo,
    SubmissionInfo,
    TriggerType,
)
from computor_agent.tutor.services.test_results import TestResultsService
from computor_agent.tutor.services.artifacts import ArtifactsService
from computor_agent.tutor.services.reference import ReferenceService
from computor_agent.tutor.services.history import HistoryService
from computor_agent.tutor.services.comments import CommentsService
from computor_agent.tutor.services.progress import ProgressService

if TYPE_CHECKING:
    from computor_agent.tutor.config import ContextConfig

logger = logging.getLogger(__name__)


class ContextBuilder:
    """
    Builds ConversationContext from API data.

    Uses ComputorClient from computor-client package directly.

    Gathers:
    - Student information from submission group
    - Previous messages
    - Course member comments (tutor/lecturer notes)
    - Student notes from filesystem
    - Student code from repository
    - Reference code (if enabled)
    - Assignment information

    Usage:
        from computor_client import ComputorClient

        async with ComputorClient(base_url=url) as client:
            await client.login(...)
            builder = ContextBuilder(client, config)
            context = await builder.build_for_message(
                submission_group_id="...",
                message={...},
            )
            # Use context, then destroy
            context.destroy()
    """

    def __init__(
        self,
        client: Any,  # ComputorClient from computor-client
        config: "ContextConfig",
    ) -> None:
        """
        Initialize the context builder.

        Args:
            client: ComputorClient instance from computor-client package
            config: Context configuration
        """
        self.client = client
        self.config = config

        # Initialize services for enhanced context
        self.test_results_service = TestResultsService(client)
        self.artifacts_service = ArtifactsService(client)
        self.reference_service = ReferenceService(client)
        self.history_service = HistoryService(client)
        self.comments_service = CommentsService(client)
        self.progress_service = ProgressService(client)

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

        # Build the basic context first
        context = ConversationContext(
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

        # Add enhanced context from services
        await self._add_enhanced_context(
            context,
            assignment_info,
            student_info,
            trigger_submission,
        )

        return context

    async def _add_enhanced_context(
        self,
        context: ConversationContext,
        assignment_info: Optional[AssignmentInfo],
        student_info: StudentInfo,
        trigger_submission: Optional[SubmissionInfo],
    ) -> None:
        """
        Add enhanced context from services.

        Modifies context in place to add:
        - Test results
        - Submission history
        - Reference comparison
        - Student progress
        - Artifact content
        """
        submission_group_id = context.submission_group_id

        # Get test results if enabled
        if self.config.include_test_results:
            try:
                context.test_results = await self.test_results_service.get_for_submission_group(
                    submission_group_id
                )
            except Exception as e:
                logger.debug(f"Failed to get test results: {e}")

        # Get submission history if enabled
        if self.config.include_submission_history:
            try:
                context.submission_history = await self.history_service.get_history(
                    submission_group_id
                )
            except Exception as e:
                logger.debug(f"Failed to get submission history: {e}")

        # Get reference comparison if enabled and we have both student and reference code
        if self.config.include_reference_comparison and context.has_code and context.has_reference:
            try:
                context.reference_comparison = self.reference_service.compare_code(
                    student_files=context.student_code.files,
                    reference_files=context.reference_code.files,
                )
            except Exception as e:
                logger.debug(f"Failed to generate reference comparison: {e}")

        # Get student progress if enabled
        if self.config.include_student_progress and assignment_info and student_info.course_member_ids:
            try:
                course_id = assignment_info.course_id
                course_member_id = student_info.course_member_ids[0]
                if course_id:
                    context.student_progress = await self.progress_service.get_member_progress(
                        course_id, course_member_id
                    )
            except Exception as e:
                logger.debug(f"Failed to get student progress: {e}")

        # Get artifact content if enabled (for submission triggers)
        if self.config.include_artifact_content and trigger_submission:
            try:
                context.artifact_content = await self.artifacts_service.download_and_extract(
                    trigger_submission.artifact_id
                )
            except Exception as e:
                logger.debug(f"Failed to get artifact content: {e}")

    async def _get_student_info(self, submission_group_id: str) -> StudentInfo:
        """Get student information from submission group."""
        try:
            # First get the submission group to find the course_id
            sg = await self.client.submission_groups.get(id=submission_group_id)
            course_id = sg.course_id

            if not course_id:
                return StudentInfo()

            # Get submission group members
            sg_members = await self.client.submission_group_members.list(
                submission_group_id=submission_group_id,
            )

            user_ids = []
            names = []
            emails = []
            course_member_ids = []

            # Get course member details for each submission group member
            for sgm in sg_members:
                course_member_id = sgm.course_member_id
                if course_member_id:
                    course_member_ids.append(course_member_id)
                    try:
                        cm = await self.client.course_members.get(id=course_member_id)
                        if cm:
                            if cm.user_id:
                                user_ids.append(cm.user_id)
                            if hasattr(cm, "display_name") and cm.display_name:
                                names.append(cm.display_name)
                            if hasattr(cm, "email") and cm.email:
                                emails.append(cm.email)
                    except Exception:
                        pass

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
            # Use ComputorClient.messages.list() directly
            messages = await self.client.messages.list(
                submission_group_id=submission_group_id,
            )

            result = []
            for msg in messages:
                # msg is a MessageList object from computor-types
                author_name = None
                if msg.author:
                    author_name = f"{msg.author.given_name or ''} {msg.author.family_name or ''}".strip()
                    if not author_name:
                        author_name = None

                result.append(
                    MessageInfo(
                        id=msg.id,
                        title=msg.title or "",
                        content=msg.content or "",
                        author_id=msg.author_id or "",
                        author_name=author_name,
                        is_from_student=True,  # Determined by checking role if needed
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
            # Use ComputorClient.submission_groups.get() directly
            sg = await self.client.submission_groups.get(id=submission_group_id)
            course_content_id = sg.course_content_id

            if not course_content_id:
                return None

            # Use ComputorClient.course_contents.get() directly
            content = await self.client.course_contents.get(id=course_content_id)

            return AssignmentInfo(
                course_content_id=course_content_id,
                title=content.title,
                description=content.description,
                course_id=content.course_id,
                course_title=getattr(content, "course_title", None),
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
            # Use ComputorClient.course_member_comments.list() directly
            comments = await self.client.course_member_comments.list(
                course_member_id=course_member_id,
            )
            # comments is list[CourseMemberCommentList] from computor-types
            return [c.content for c in comments if c.content]
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
