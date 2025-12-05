"""
Trigger detection for the Tutor AI Agent.

Determines when the tutor agent should respond based on:
1. Message triggers: Student wrote the last message (unanswered by staff)
2. Submission triggers: New submission artifact with submit=True

Course roles that count as "staff" (can answer students):
- _tutor
- _lecturer
- _maintainer
- _owner

Course roles that count as "student" (need answers):
- _student
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Protocol

logger = logging.getLogger(__name__)


# Staff roles - these users can answer students
STAFF_ROLES = {"_tutor", "_lecturer", "_maintainer", "_owner"}

# Student role - these users need answers
STUDENT_ROLE = "_student"


@dataclass
class MessageTrigger:
    """Information about a message that triggers the tutor."""

    message_id: str
    submission_group_id: str
    author_id: str
    author_course_member_id: str
    author_role: str
    content: str
    title: str
    created_at: Optional[datetime] = None


@dataclass
class SubmissionTrigger:
    """Information about a submission that triggers the tutor."""

    artifact_id: str
    submission_group_id: str
    uploaded_by_course_member_id: Optional[str]
    version_identifier: Optional[str]
    file_size: int
    uploaded_at: Optional[datetime] = None


@dataclass
class TriggerCheckResult:
    """Result of checking if the tutor should respond."""

    should_respond: bool
    """True if the tutor should generate a response."""

    reason: str
    """Human-readable reason for the decision."""

    message_trigger: Optional[MessageTrigger] = None
    """The message that triggered (if message trigger)."""

    submission_trigger: Optional[SubmissionTrigger] = None
    """The submission that triggered (if submission trigger)."""


class ComputorClientProtocol(Protocol):
    """Protocol for the Computor API client."""

    async def list(self, **kwargs) -> list:
        """List resources."""
        ...


class TriggerChecker:
    """
    Checks if the tutor agent should respond to a submission group.

    The tutor should respond when:
    1. A student wrote the last message AND no staff has replied after it
    2. A new submission artifact with submit=True is created

    Usage:
        checker = TriggerChecker(messages_client, course_members_client, submissions_client)

        # Check if should respond to messages
        result = await checker.check_message_trigger(submission_group_id, course_id)
        if result.should_respond:
            # Process result.message_trigger
            pass

        # Check if should respond to submission
        result = await checker.check_submission_trigger(submission_group_id, artifact)
        if result.should_respond:
            # Process result.submission_trigger
            pass
    """

    def __init__(
        self,
        messages_client: ComputorClientProtocol,
        course_members_client: ComputorClientProtocol,
        submissions_client: Optional[ComputorClientProtocol] = None,
    ) -> None:
        """
        Initialize the trigger checker.

        Args:
            messages_client: Client for messages API
            course_members_client: Client for course_members API
            submissions_client: Client for submissions API (optional)
        """
        self.messages = messages_client
        self.course_members = course_members_client
        self.submissions = submissions_client

        # Cache for course_member role lookups
        self._role_cache: dict[str, str] = {}

    async def check_message_trigger(
        self,
        submission_group_id: str,
        course_id: str,
    ) -> TriggerCheckResult:
        """
        Check if the tutor should respond based on messages.

        The tutor should respond when:
        - The last message was written by a student (_student role)
        - No staff member has replied after that message

        Args:
            submission_group_id: The submission group to check
            course_id: The course ID (for looking up course members)

        Returns:
            TriggerCheckResult indicating if/why to respond
        """
        try:
            # Get messages for this submission group, ordered by created_at
            messages = await self.messages.list(
                submission_group_id=submission_group_id,
                limit=50,  # Get recent messages
            )

            if not messages:
                return TriggerCheckResult(
                    should_respond=False,
                    reason="No messages in submission group",
                )

            # Sort by created_at (most recent last)
            # Note: Assuming messages have created_at attribute
            messages_sorted = sorted(
                messages,
                key=lambda m: getattr(m, "created_at", datetime.min) or datetime.min,
            )

            # Get the last message
            last_message = messages_sorted[-1]

            # Look up the author's course role
            author_id = last_message.author_id
            author_role = await self._get_author_role(author_id, course_id)

            if author_role is None:
                return TriggerCheckResult(
                    should_respond=False,
                    reason=f"Could not determine role for author {author_id}",
                )

            # Check if the author is a student
            if author_role not in STAFF_ROLES:
                # Author is a student - check if any staff replied after
                # Since this is the last message and they're a student, no staff has replied
                course_member = await self._get_course_member_by_user_id(author_id, course_id)

                return TriggerCheckResult(
                    should_respond=True,
                    reason=f"Last message from student (role: {author_role}) needs response",
                    message_trigger=MessageTrigger(
                        message_id=last_message.id,
                        submission_group_id=submission_group_id,
                        author_id=author_id,
                        author_course_member_id=course_member.id if course_member else "",
                        author_role=author_role,
                        content=last_message.content,
                        title=last_message.title,
                        created_at=getattr(last_message, "created_at", None),
                    ),
                )
            else:
                return TriggerCheckResult(
                    should_respond=False,
                    reason=f"Last message from staff (role: {author_role})",
                )

        except Exception as e:
            logger.exception(f"Error checking message trigger: {e}")
            return TriggerCheckResult(
                should_respond=False,
                reason=f"Error checking trigger: {e}",
            )

    async def check_submission_trigger(
        self,
        submission_group_id: str,
        artifact: dict,
    ) -> TriggerCheckResult:
        """
        Check if a submission artifact should trigger a review.

        Args:
            submission_group_id: The submission group
            artifact: The submission artifact dict (must have submit=True)

        Returns:
            TriggerCheckResult indicating if/why to respond
        """
        # Check if this is an official submission
        if not artifact.get("submit", False):
            return TriggerCheckResult(
                should_respond=False,
                reason="Artifact is not marked as submit=True",
            )

        return TriggerCheckResult(
            should_respond=True,
            reason="New submission artifact with submit=True",
            submission_trigger=SubmissionTrigger(
                artifact_id=artifact.get("id", ""),
                submission_group_id=submission_group_id,
                uploaded_by_course_member_id=artifact.get("uploaded_by_course_member_id"),
                version_identifier=artifact.get("version_identifier"),
                file_size=artifact.get("file_size", 0),
                uploaded_at=artifact.get("uploaded_at"),
            ),
        )

    async def _get_author_role(
        self,
        user_id: str,
        course_id: str,
    ) -> Optional[str]:
        """
        Get the course role for a user.

        Args:
            user_id: The user ID
            course_id: The course ID

        Returns:
            The course_role_id or None if not found
        """
        cache_key = f"{user_id}:{course_id}"

        if cache_key in self._role_cache:
            return self._role_cache[cache_key]

        course_member = await self._get_course_member_by_user_id(user_id, course_id)

        if course_member:
            role = course_member.course_role_id
            self._role_cache[cache_key] = role
            return role

        return None

    async def _get_course_member_by_user_id(
        self,
        user_id: str,
        course_id: str,
    ):
        """Get course member by user_id and course_id."""
        try:
            members = await self.course_members.get_course_members(
                user_id=user_id,
                course_id=course_id,
                limit=1,
            )
            return members[0] if members else None
        except Exception as e:
            logger.warning(f"Failed to get course member: {e}")
            return None

    def clear_cache(self) -> None:
        """Clear the role cache."""
        self._role_cache.clear()

    def is_student_role(self, role: str) -> bool:
        """Check if a role is a student role."""
        return role not in STAFF_ROLES

    def is_staff_role(self, role: str) -> bool:
        """Check if a role is a staff role."""
        return role in STAFF_ROLES


async def should_tutor_respond(
    messages_client: ComputorClientProtocol,
    course_members_client: ComputorClientProtocol,
    submission_group_id: str,
    course_id: str,
) -> TriggerCheckResult:
    """
    Convenience function to check if tutor should respond.

    Args:
        messages_client: Client for messages API
        course_members_client: Client for course_members API
        submission_group_id: The submission group to check
        course_id: The course ID

    Returns:
        TriggerCheckResult
    """
    checker = TriggerChecker(messages_client, course_members_client)
    return await checker.check_message_trigger(submission_group_id, course_id)
