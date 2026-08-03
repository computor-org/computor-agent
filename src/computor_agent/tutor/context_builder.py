"""
Context builder for the Tutor AI Agent.

Builds ConversationContext from API data, gathering all required
information before processing a student interaction.

Uses ComputorClient from computor-client package directly.
Accepts pre-fetched CourseContentStudentGet to avoid redundant API calls.
"""

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from computor_types.messages import MessageThread
from computor_types.student_course_contents import CourseContentStudentGet

from computor_agent.tutor.context import (
    AssignmentInfo,
    CodeContext,
    ConversationContext,
    MessageInfo,
    StudentInfo,
    TriggerType,
)
from computor_agent.tutor.services.test_results import TestResultsService
from computor_agent.tutor.services.artifacts import ArtifactsService
from computor_agent.tutor.services.reference import ReferenceService
from computor_agent.tutor.services.history import HistoryService
from computor_agent.tutor.services.progress import ProgressService

if TYPE_CHECKING:
    from computor_agent.tutor.assignment_loader import AssignmentContext
    from computor_agent.tutor.config import ContextConfig, FigureReviewConfig

logger = logging.getLogger(__name__)


def take_recent_messages(messages: list, limit: int) -> list:
    """The last ``limit`` messages of a conversation.

    ``previous_messages`` is ordered "most recent last", so truncation has to
    take the TAIL. Slicing from the front (as this used to) handed the agent the
    opening turns of a long thread and dropped everything the student had just
    said - the wrong half for answering a follow-up.

    ``limit <= 0`` means "no history"; note that ``messages[-0:]`` would return
    the entire list, so the guard is not redundant.
    """
    if limit <= 0:
        return []
    return messages[-limit:]


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
        figure_config: Optional["FigureReviewConfig"] = None,
    ) -> None:
        """
        Initialize the context builder.

        Args:
            client: ComputorClient instance from computor-client package
            config: Context configuration
            figure_config: Figure review configuration (images are collected
                from submissions only when this is provided and enabled)
        """
        self.client = client
        self.config = config
        self.figure_config = figure_config

        # Initialize services for enhanced context
        self.test_results_service = TestResultsService(client)
        self.artifacts_service = ArtifactsService(client)
        self.reference_service = ReferenceService(client, cache_dir=config.cache_dir)
        self.history_service = HistoryService(client)
        self.progress_service = ProgressService(client)

    @property
    def _collect_images(self) -> bool:
        """Whether figure collection is active."""
        return self.figure_config is not None and self.figure_config.enabled

    async def build_for_message(
        self,
        submission_group_id: str,
        message: dict,
        repository_path: Optional[Path] = None,
        reference_path: Optional[Path] = None,
        course_content: Optional[CourseContentStudentGet] = None,
        course_member_id: Optional[str] = None,
        assignment_context: Optional["AssignmentContext"] = None,
    ) -> ConversationContext:
        """
        Build context for a message trigger.

        Args:
            submission_group_id: The submission group ID
            message: The message dict that triggered this
            repository_path: Path to student's cloned repository
            reference_path: Path to reference solution (if enabled)
            course_content: Pre-fetched CourseContentStudentGet to avoid redundant API calls
            course_member_id: Course member ID (for efficient data extraction)
            assignment_context: Assignment context from dev mode (skips API calls for description)

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
            thread_root_id=message.get("thread_root_id"),
        )

        return await self._build_context(
            submission_group_id=submission_group_id,
            trigger_message=trigger_message,
            repository_path=repository_path,
            reference_path=reference_path,
            course_content=course_content,
            course_member_id=course_member_id,
            assignment_context=assignment_context,
        )

    async def _build_context(
        self,
        submission_group_id: str,
        trigger_message: MessageInfo,
        repository_path: Optional[Path],
        reference_path: Optional[Path],
        course_content: Optional[CourseContentStudentGet] = None,
        course_member_id: Optional[str] = None,
        assignment_context: Optional["AssignmentContext"] = None,
    ) -> ConversationContext:
        """Build the full context with all gathered data."""
        # If course_content is provided, extract student and assignment info directly
        # This avoids redundant API calls to /submission-groups, /submission-group-members, /course-contents
        if course_content is not None:
            student_info = self._extract_student_info(course_content, course_member_id)
            # Use assignment_context description if available (dev mode), skip API call
            if assignment_context:
                assignment_info = AssignmentInfo(
                    course_content_id=course_content.id,
                    title=assignment_context.title,
                    description=assignment_context.readme_content,
                    course_id=course_content.course_id,
                    course_title=None,
                )
            else:
                assignment_info = await self._extract_assignment_info(course_content)
        else:
            # Fallback: Gather data via API calls (for backward compatibility)
            student_info = await self._get_student_info(submission_group_id)
            assignment_info = await self._get_assignment_info(submission_group_id)

        # Use thread endpoint for follow-ups (focused conversation history),
        # fall back to all submission group messages otherwise
        thread_root_id = trigger_message.thread_root_id if hasattr(trigger_message, 'thread_root_id') else None
        if thread_root_id:
            previous_messages = await self._get_thread_messages(thread_root_id)
        else:
            previous_messages = await self._get_previous_messages(submission_group_id)

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

        # Load reference code if a reference path was provided. The reference
        # solution is always included in context.
        reference_code: Optional[CodeContext] = None
        if reference_path and reference_path.exists():
            reference_code = self._load_code_from_path(
                reference_path,
                max_lines=self.config.max_code_lines,
                max_files=self.config.max_code_files,
            )

        # Build the basic context first
        context = ConversationContext(
            trigger_type=TriggerType.MESSAGE,
            submission_group_id=submission_group_id,
            trigger_message=trigger_message,
            student=student_info,
            assignment=assignment_info,
            previous_messages=take_recent_messages(
                previous_messages, self.config.include_previous_messages
            ),
            course_member_comments=[],  # Not implemented - endpoint not available
            student_notes=student_notes,
            student_code=student_code,
            reference_code=reference_code,
        )

        # Add enhanced context from services
        await self._add_enhanced_context(
            context,
            assignment_info,
            student_info,
            course_content,  # Pass pre-fetched data if available
        )

        return context

    async def download_submission_code(
        self,
        submission_group_id: Optional[str] = None,
        course_content_id: Optional[str] = None,
        course_member_id: Optional[str] = None,
        submit_only: bool = False,
    ) -> Optional[CodeContext]:
        """
        Download the latest submission as code context.

        Args:
            submission_group_id: Submission group ID (use this OR course_content_id+course_member_id)
            course_content_id: Course content ID (use with course_member_id)
            course_member_id: Course member ID (use with course_content_id)
            submit_only: If True, only get official submissions. If False, include test uploads

        Returns:
            CodeContext with submission files, or None if no submission found
        """
        image_kwargs: dict[str, Any] = {}
        if self._collect_images:
            image_kwargs = {
                "collect_images": True,
                "image_extensions": self.figure_config.extension_set(),
                "max_figures": self.figure_config.max_figures,
                "max_image_bytes": self.figure_config.max_image_bytes,
            }

        artifact_content = await self.artifacts_service.download_latest_submission(
            submission_group_id=submission_group_id,
            course_content_id=course_content_id,
            course_member_id=course_member_id,
            submit_only=submit_only,
            max_files=self.config.max_code_files,
            max_total_size=10 * 1024 * 1024,  # 10MB max
            **image_kwargs,
        )

        if not artifact_content:
            return None

        # Convert ArtifactContent to CodeContext
        total_lines = sum(content.count('\n') + 1 for content in artifact_content.files.values())

        return CodeContext(
            files=artifact_content.files,
            total_lines=total_lines,
            repository_path=None,  # No local path for downloaded submissions
            truncated=artifact_content.truncated,
            is_submission=True,  # Mark this as a submission download
            images=artifact_content.image_files,
        )

    async def _add_enhanced_context(
        self,
        context: ConversationContext,
        assignment_info: Optional[AssignmentInfo],
        student_info: StudentInfo,
        course_content_data: Optional[CourseContentStudentGet] = None,
    ) -> None:
        """
        Add enhanced context from services.

        Modifies context in place to add:
        - Test results
        - Submission history
        - Reference comparison
        - Student progress
        - Downloaded submission code (if not already loaded)

        Args:
            course_content_data: Pre-fetched CourseContentStudentGet to avoid redundant API calls.
                If provided, uses this data directly. Otherwise falls back to API call.
        """
        submission_group_id = context.submission_group_id

        # Get course member and course content IDs for the primary tutor endpoint
        course_member_id = student_info.course_member_ids[0] if student_info.course_member_ids else None
        course_content_id = assignment_info.course_content_id if assignment_info else None

        # Use pre-fetched course content data if available, otherwise fetch from API
        if course_content_data is None and course_member_id and course_content_id:
            try:
                if hasattr(self.client, 'tutors'):
                    course_content_data = await self.client.tutors.get_course_members_course_contents(
                        course_member_id, course_content_id
                    )
                    logger.debug(
                        f"Fetched course content data for member={course_member_id}, "
                        f"content={course_content_id}"
                    )
            except Exception as e:
                logger.debug(f"Failed to fetch course content data: {e}")

        # Get test results from course content data
        if self.config.include_test_results:
            try:
                if course_content_data:
                    # Extract result from course content data
                    result_data = getattr(course_content_data, "result", None)
                    if result_data:
                        context.test_results = self.test_results_service._parse_result(result_data)
                    # If course_content_data exists but no result, skip (no tests run yet)
                elif course_member_id and course_content_id:
                    # Only fallback if we don't have pre-fetched data at all
                    context.test_results = await self.test_results_service.get_for_course_content(
                        course_member_id, course_content_id
                    )
            except Exception as e:
                logger.debug(f"Failed to get test results: {e}")

        # Submission history — disabled (not used in prompt currently)
        # if self.config.include_submission_history:
        #     ...

        # Get reference comparison if enabled and we have both student and reference code
        if self.config.include_reference_comparison and context.has_code and context.has_reference:
            try:
                context.reference_comparison = self.reference_service.compare_code(
                    student_files=context.student_code.files,
                    reference_files=context.reference_code.files,
                )
            except Exception as e:
                logger.debug(f"Failed to generate reference comparison: {e}")

        # Student progress — disabled (not used in prompt currently)
        # if self.config.include_student_progress and assignment_info and course_member_id:
        #     ...

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

    async def _get_thread_messages(
        self,
        thread_root_id: str,
    ) -> list[MessageInfo]:
        """Get all messages in a conversation thread.

        Uses the /messages/{id}/thread endpoint to fetch the full thread
        starting from the root message. This provides focused conversation
        context for follow-up messages.
        """
        try:
            thread_raw = await self.client.messages.thread(thread_root_id)
            thread = MessageThread.model_validate(thread_raw)

            result = []
            for msg in thread.messages:
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

            logger.info(f"Fetched {len(result)} messages from thread (root={thread_root_id})")
            return result
        except Exception as e:
            logger.warning(f"Failed to get thread messages for {thread_root_id}: {e}")
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

            # Get the full README/description from tutor API
            description = await self.reference_service.get_description(course_content_id)
            if description:
                logger.info(f"Fetched assignment description for {course_content_id}")
            else:
                logger.warning(f"No assignment description available for {course_content_id}")

            return AssignmentInfo(
                course_content_id=course_content_id,
                title=content.title,
                description=description,
                course_id=content.course_id,
                course_title=getattr(content, "course_title", None),
            )
        except Exception as e:
            logger.warning(f"Failed to get assignment info: {e}")
            return None

    def _extract_student_info(
        self,
        course_content: CourseContentStudentGet,
        course_member_id: Optional[str] = None,
    ) -> StudentInfo:
        """
        Extract student information from pre-fetched CourseContentStudentGet.

        This avoids redundant API calls to /submission-groups and /submission-group-members.

        Args:
            course_content: Pre-fetched CourseContentStudentGet
            course_member_id: Course member ID (if known from scheduler)

        Returns:
            StudentInfo extracted from course content
        """
        user_ids = []
        names = []
        emails = []
        course_member_ids = []

        # Extract from submission_group.members if available
        sg = course_content.submission_group
        if sg and sg.members:
            for member in sg.members:
                if member.user_id:
                    user_ids.append(member.user_id)
                if member.course_member_id:
                    course_member_ids.append(member.course_member_id)
                if member.full_name:
                    names.append(member.full_name)
                if member.username:
                    # Username can be used as fallback for name
                    if not member.full_name:
                        names.append(member.username)

        # If course_member_id was provided but not in members, add it
        if course_member_id and course_member_id not in course_member_ids:
            course_member_ids.append(course_member_id)

        return StudentInfo(
            user_ids=user_ids,
            names=names,
            emails=emails,
            course_member_ids=course_member_ids,
        )

    async def _extract_assignment_info(
        self,
        course_content: CourseContentStudentGet,
    ) -> Optional[AssignmentInfo]:
        """
        Extract assignment information from pre-fetched CourseContentStudentGet.

        Also fetches the full README/description from the tutor API.

        Args:
            course_content: Pre-fetched CourseContentStudentGet

        Returns:
            AssignmentInfo extracted from course content
        """
        # Get the full README/description from tutor API
        description = await self.reference_service.get_description(course_content.id)
        if description:
            logger.info(f"Fetched assignment description for {course_content.id}")
        else:
            logger.warning(f"No assignment description available for {course_content.id}")

        return AssignmentInfo(
            course_content_id=course_content.id,
            title=course_content.title,
            description=description,
            course_id=course_content.course_id,
            course_title=None,  # Not available in CourseContentStudentGet
        )

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
                        content = file_path.read_text(encoding="utf-8", errors="replace")
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

        images: list = []
        if self._collect_images:
            from computor_agent.tutor.figures.detection import collect_images_from_dir

            images, skipped = collect_images_from_dir(
                repo_path,
                extensions=self.figure_config.extension_set(),
                max_figures=self.figure_config.max_figures,
                max_image_bytes=self.figure_config.max_image_bytes,
                skip_dirs=skip_dirs,
            )
            if skipped:
                logger.info(f"Figures skipped due to limits: {', '.join(skipped)}")

        return CodeContext(
            files=files,
            total_lines=total_lines,
            repository_path=repo_path,
            truncated=truncated,
            images=images,
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
            notes_dir = Path(self.config.student_notes_dir).resolve()
            notes_dir.mkdir(parents=True, exist_ok=True)

            # Sanitize user_id to prevent path traversal
            safe_user_id = "".join(c for c in user_id if c.isalnum() or c in "-_")
            if not safe_user_id:
                logger.warning(f"Invalid user_id for notes: {user_id!r}")
                return False

            notes_path = (notes_dir / f"{safe_user_id}.txt").resolve()
            if not str(notes_path).startswith(str(notes_dir)):
                logger.warning(f"Path traversal attempt in student notes: {user_id!r}")
                return False

            notes_path.write_text(notes)
            return True
        except Exception as e:
            logger.error(f"Failed to save student notes: {e}")
            return False
