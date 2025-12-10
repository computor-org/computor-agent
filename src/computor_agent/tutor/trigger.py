"""
Trigger detection for the Tutor AI Agent.

Determines when the tutor agent should respond based on:
1. Message triggers: Messages tagged with configured request tags (e.g., #ai::request)
2. Submission triggers: New submission artifact with submit=True

The agent uses tag-based filtering to:
- Find messages that request AI assistance (configurable request_tags)
- Avoid duplicate responses by checking for response_tag
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Protocol

from computor_agent.tutor.config import TriggerConfig

logger = logging.getLogger(__name__)


# Staff roles - these users can answer students (kept for backwards compatibility)
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


class MessagesClientProtocol(Protocol):
    """Protocol for the messages API client."""

    async def list(self, **kwargs) -> list:
        """List messages with optional filters."""
        ...


class CourseMembersClientProtocol(Protocol):
    """Protocol for the course_members API client."""

    async def get_course_members(self, **kwargs) -> list:
        """Get course members."""
        ...


class TriggerChecker:
    """
    Checks if the tutor agent should respond based on message tags.

    The tutor should respond when:
    1. A message has a configured request tag (e.g., #ai::request)
    2. No response with the response tag exists yet for that submission group
    3. A new submission artifact with submit=True is created (if enabled)

    Usage:
        config = TriggerConfig(
            request_tags=[TriggerTag(scope="ai", value="request")],
            response_tag=TriggerTag(scope="ai", value="response"),
        )
        checker = TriggerChecker(messages_client, course_members_client, config)

        # Check if should respond to messages in a submission group
        result = await checker.check_message_trigger(submission_group_id, course_id)
        if result.should_respond:
            # Process result.message_trigger
            pass
    """

    def __init__(
        self,
        messages_client: MessagesClientProtocol,
        course_members_client: CourseMembersClientProtocol,
        config: Optional[TriggerConfig] = None,
    ) -> None:
        """
        Initialize the trigger checker.

        Args:
            messages_client: Client for messages API
            course_members_client: Client for course_members API
            config: Trigger configuration (uses defaults if not provided)
        """
        self.messages = messages_client
        self.course_members = course_members_client
        self.config = config or TriggerConfig()

        # Cache for course_member role lookups
        self._role_cache: dict[str, str] = {}

    async def check_message_trigger(
        self,
        submission_group_id: str,
        course_id: str,
    ) -> TriggerCheckResult:
        """
        Check if the tutor should respond based on message tags.

        The tutor should respond when:
        - A message in the submission group has a configured request tag
        - No message with the response tag exists yet (to avoid duplicates)

        Args:
            submission_group_id: The submission group to check
            course_id: The course ID (for looking up course members)

        Returns:
            TriggerCheckResult indicating if/why to respond
        """
        if not self.config.is_enabled:
            return TriggerCheckResult(
                should_respond=False,
                reason="Tag-based triggers are disabled (no request_tags defined)",
            )

        try:
            # First, check if we already responded (has response tag)
            existing_responses = await self.messages.list(
                submission_group_id=submission_group_id,
                tag_scope=self.config.response_tag.scope,
            )

            # Filter to only messages with the exact response tag
            response_tag = self.config.response_tag_string
            has_response = any(
                response_tag in (getattr(m, "title", "") or "")
                for m in existing_responses
            )

            if has_response:
                return TriggerCheckResult(
                    should_respond=False,
                    reason=f"Already responded (found #{response_tag} tag)",
                )

            # Query for messages with request tags
            request_messages = await self.messages.list(
                submission_group_id=submission_group_id,
                tags=self.config.request_tag_strings,
                tags_match_all=self.config.require_all_tags,
            )

            if not request_messages:
                return TriggerCheckResult(
                    should_respond=False,
                    reason="No messages with request tags found",
                )

            # Sort by created_at (oldest first to process in order)
            messages_sorted = sorted(
                request_messages,
                key=lambda m: getattr(m, "created_at", datetime.min) or datetime.min,
            )

            # Get the oldest request message
            message = messages_sorted[0]
            author_id = getattr(message, "author_id", "")

            # Get author info
            author_role = ""
            author_course_member_id = ""

            # Try to get author_course_member info if available
            author_cm = getattr(message, "author_course_member", None)
            if author_cm:
                author_role = getattr(author_cm, "course_role_id", "") or ""
                author_course_member_id = getattr(author_cm, "id", "") or ""
            else:
                # Fall back to looking up course member
                course_member = await self._get_course_member_by_user_id(
                    author_id, course_id
                )
                if course_member:
                    author_role = getattr(course_member, "course_role_id", "") or ""
                    author_course_member_id = getattr(course_member, "id", "") or ""

            return TriggerCheckResult(
                should_respond=True,
                reason=f"Found message with request tag(s): {self.config.request_tag_strings}",
                message_trigger=MessageTrigger(
                    message_id=getattr(message, "id", ""),
                    submission_group_id=submission_group_id,
                    author_id=author_id,
                    author_course_member_id=author_course_member_id,
                    author_role=author_role,
                    content=getattr(message, "content", "") or "",
                    title=getattr(message, "title", "") or "",
                    created_at=getattr(message, "created_at", None),
                ),
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

        Also checks if a response already exists (via response tag) to avoid
        duplicate reviews.

        Args:
            submission_group_id: The submission group
            artifact: The submission artifact dict (must have submit=True)

        Returns:
            TriggerCheckResult indicating if/why to respond
        """
        if not self.config.check_submissions:
            return TriggerCheckResult(
                should_respond=False,
                reason="Submission triggers are disabled",
            )

        # Check if this is an official submission
        if not artifact.get("submit", False):
            return TriggerCheckResult(
                should_respond=False,
                reason="Artifact is not marked as submit=True",
            )

        # Check if we already responded to this submission group
        try:
            existing_responses = await self.messages.list(
                submission_group_id=submission_group_id,
                tag_scope=self.config.response_tag.scope,
            )

            response_tag = self.config.response_tag_string
            has_response = any(
                response_tag in (getattr(m, "title", "") or "")
                for m in existing_responses
            )

            if has_response:
                return TriggerCheckResult(
                    should_respond=False,
                    reason=f"Already responded to submission (found #{response_tag} tag)",
                )
        except Exception as e:
            logger.warning(f"Could not check for existing responses: {e}")
            # Continue anyway - better to potentially duplicate than miss

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

    async def _get_course_member_by_user_id(
        self,
        user_id: str,
        course_id: str,
    ):
        """Get course member by user_id and course_id."""
        if not user_id or not course_id:
            return None

        try:
            members = await self.course_members.get_course_members(
                user_id=user_id,
                course_id=course_id,
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
    messages_client: MessagesClientProtocol,
    course_members_client: CourseMembersClientProtocol,
    submission_group_id: str,
    course_id: str,
    config: Optional[TriggerConfig] = None,
) -> TriggerCheckResult:
    """
    Convenience function to check if tutor should respond.

    Args:
        messages_client: Client for messages API
        course_members_client: Client for course_members API
        submission_group_id: The submission group to check
        course_id: The course ID
        config: Trigger configuration (uses defaults if not provided)

    Returns:
        TriggerCheckResult
    """
    checker = TriggerChecker(messages_client, course_members_client, config)
    return await checker.check_message_trigger(submission_group_id, course_id)
