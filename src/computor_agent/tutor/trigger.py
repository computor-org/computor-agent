"""
Trigger detection for the Tutor AI Agent.

Determines when the tutor agent should respond based on:
1. Message triggers: Messages tagged with configured request tags (e.g., #ai::request)
2. Reply chain triggers: Unread replies to AI responses (in same message chain)
3. Submission triggers: New submission artifact with submit=True

Conversation model:
- A conversation is a chain of messages linked by parent_id
- Conversation starts when a message has a configured request tag
- If the AI replies, any student reply to that chain triggers a new response
- No external state needed - the message chain IS the conversation
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Protocol, Union

# Import API types from computor-types (source of truth)
from computor_types.artifacts import SubmissionArtifactList
from computor_types.course_members import CourseMemberList
from computor_types.messages import MessageGet, MessageList

from computor_agent.tutor.config import TriggerConfig

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

    # Conversation context
    root_message_id: Optional[str] = None
    """Root message ID of the conversation (the message with request tag)."""

    parent_id: Optional[str] = None
    """ID of the message this is replying to (None if root message)."""

    is_follow_up: bool = False
    """True if this is a follow-up reply in an existing conversation."""


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

    root_message_id: Optional[str] = None
    """Root message ID of the conversation (for context building)."""


class MessagesClientProtocol(Protocol):
    """Protocol for the messages API client."""

    async def list(self, **kwargs) -> list[MessageList]:
        """List messages with optional filters."""
        ...

    async def get(self, id: str, **kwargs) -> MessageGet:
        """Get a single message by ID."""
        ...


class CourseMembersClientProtocol(Protocol):
    """Protocol for the course_members API client."""

    async def list(self, **kwargs) -> list[CourseMemberList]:
        """List course members with optional filters."""
        ...


class TriggerChecker:
    """
    Checks if the tutor agent should respond based on message tags and reply chains.

    The tutor should respond when:
    1. A message has a configured request tag (starts new conversation)
    2. An unread reply exists to a message chain where AI already responded
    3. A new submission artifact with submit=True is created

    No external conversation state is needed - the message chain (parent_id links)
    defines the conversation, and AI response tags identify where the AI participated.

    Usage:
        checker = TriggerChecker(messages_client, course_members_client, config)

        # Check for triggers in a submission group
        result = await checker.check_message_trigger(submission_group_id, course_id)
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
        Check if the tutor should respond to messages.

        Checks for:
        1. New messages with request tags (starts conversation)
        2. Unread replies in conversations where AI already participated

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
            # Step 1: Check for new messages with request tags
            result = await self._check_new_conversation_trigger(
                submission_group_id, course_id
            )
            if result.should_respond:
                return result

            # Step 2: Check for follow-up replies to AI responses
            result = await self._check_follow_up_trigger(
                submission_group_id, course_id
            )
            if result.should_respond:
                return result

            return TriggerCheckResult(
                should_respond=False,
                reason="No new request tags or follow-ups found",
            )

        except Exception as e:
            logger.exception(f"Error checking message trigger: {e}")
            return TriggerCheckResult(
                should_respond=False,
                reason=f"Error checking trigger: {e}",
            )

    async def _check_new_conversation_trigger(
        self,
        submission_group_id: str,
        course_id: str,
    ) -> TriggerCheckResult:
        """Check for new messages with request tags that start a conversation."""

        # Query for messages with request tags
        request_messages = await self.messages.list(
            submission_group_id=submission_group_id,
            tags=self.config.request_tag_strings,
            tags_match_all=self.config.require_all_tags,
            unread=True,  # Only unread messages
        )

        if not request_messages:
            return TriggerCheckResult(
                should_respond=False,
                reason="No unread messages with request tags found",
            )

        # Sort by created_at (oldest first to process in order)
        messages_sorted = sorted(
            request_messages,
            key=lambda m: getattr(m, "created_at", datetime.min) or datetime.min,
        )

        # Get the oldest unread request message
        message = messages_sorted[0]
        message_id = getattr(message, "id", "")

        # Build trigger info
        trigger = await self._build_message_trigger(
            message, submission_group_id, course_id
        )
        trigger.root_message_id = message_id  # This message is the root
        trigger.is_follow_up = False

        return TriggerCheckResult(
            should_respond=True,
            reason=f"New conversation: message with request tag(s): {self.config.request_tag_strings}",
            message_trigger=trigger,
            root_message_id=message_id,
        )

    async def _check_follow_up_trigger(
        self,
        submission_group_id: str,
        course_id: str,
    ) -> TriggerCheckResult:
        """
        Check for unread follow-up messages in conversations where AI participated.

        The AI should respond to any unread reply in a chain where:
        - The AI previously responded (message has response_tag in title)
        - The reply is from a student (not staff)
        """

        # Get all unread messages in this submission group
        unread_messages = await self.messages.list(
            submission_group_id=submission_group_id,
            unread=True,
        )

        if not unread_messages:
            return TriggerCheckResult(
                should_respond=False,
                reason="No unread messages",
            )

        # Find messages that are replies (have parent_id)
        for message in unread_messages:
            parent_id = getattr(message, "parent_id", None)
            if not parent_id:
                continue

            # Check if author is a student (not staff/agent)
            author_role = await self._get_author_role_from_message(message, course_id)
            if author_role in STAFF_ROLES:
                continue

            # Trace up the chain to find if AI participated
            root_id = await self._find_ai_conversation_root(parent_id)

            if root_id:
                # Found a conversation where AI participated - respond to this follow-up
                trigger = await self._build_message_trigger(
                    message, submission_group_id, course_id
                )
                trigger.root_message_id = root_id
                trigger.parent_id = parent_id
                trigger.is_follow_up = True

                return TriggerCheckResult(
                    should_respond=True,
                    reason=f"Follow-up reply in conversation (root: {root_id})",
                    message_trigger=trigger,
                    root_message_id=root_id,
                )

        return TriggerCheckResult(
            should_respond=False,
            reason="No follow-up messages requiring response",
        )

    async def _find_ai_conversation_root(
        self,
        message_id: str,
        max_depth: int = 50,
    ) -> Optional[str]:
        """
        Trace up the parent chain to find the root of a conversation where AI participated.

        The AI participated if any message in the chain has:
        - The response_tag in its title (AI's own response)
        - A request_tag in its title (conversation start)

        Args:
            message_id: The message ID to start from (parent of the new message)
            max_depth: Maximum depth to traverse (prevents infinite loops)

        Returns:
            The root message ID if AI participated, None otherwise
        """
        current_id = message_id
        visited = set()
        found_ai_response = False
        root_id = None

        for _ in range(max_depth):
            if current_id in visited:
                break
            visited.add(current_id)

            try:
                message = await self.messages.get(id=current_id)
                title = getattr(message, "title", "") or ""
                parent_id = getattr(message, "parent_id", None)

                # Check if this message is an AI response
                if self.config.response_tag_string in title:
                    found_ai_response = True

                # Check if this message has a request tag (conversation start)
                for tag in self.config.request_tag_strings:
                    if tag in title:
                        root_id = current_id
                        break

                if not parent_id:
                    # Reached the root of the chain
                    if root_id is None:
                        root_id = current_id
                    break

                current_id = parent_id

            except Exception as e:
                logger.warning(f"Failed to get message {current_id}: {e}")
                break

        # Only return root if AI participated in this conversation
        return root_id if found_ai_response else None

    async def _build_message_trigger(
        self,
        message: Union[MessageList, MessageGet],
        submission_group_id: str,
        course_id: str,
    ) -> MessageTrigger:
        """Build a MessageTrigger from a MessageList or MessageGet object."""
        author_id = message.author_id
        author_role = ""
        author_course_member_id = ""

        # Try to get author info from embedded data (MessageAuthorCourseMember)
        author_cm = message.author_course_member
        if author_cm:
            author_role = author_cm.course_role_id or ""
            author_course_member_id = author_cm.id or ""
        else:
            # Fall back to lookup
            course_member = await self._get_course_member_by_user_id(author_id, course_id)
            if course_member:
                author_role = course_member.course_role_id or ""
                author_course_member_id = course_member.id or ""

        return MessageTrigger(
            message_id=message.id,
            submission_group_id=submission_group_id,
            author_id=author_id,
            author_course_member_id=author_course_member_id,
            author_role=author_role,
            content=message.content or "",
            title=message.title or "",
            created_at=message.created_at if hasattr(message, "created_at") else None,
            parent_id=message.parent_id,
        )

    async def _get_author_role_from_message(
        self, message: Union[MessageList, MessageGet], course_id: str
    ) -> str:
        """Get the author's role from a message."""
        author_cm = message.author_course_member
        if author_cm:
            return author_cm.course_role_id or ""

        author_id = message.author_id
        if author_id:
            course_member = await self._get_course_member_by_user_id(author_id, course_id)
            if course_member:
                return course_member.course_role_id or ""

        return ""

    async def check_submission_trigger(
        self,
        submission_group_id: str,
        artifact: Union[SubmissionArtifactList, dict],
    ) -> TriggerCheckResult:
        """
        Check if a submission artifact should trigger a review.

        Args:
            submission_group_id: The submission group
            artifact: The submission artifact (SubmissionArtifactList or dict with submit=True)

        Returns:
            TriggerCheckResult indicating if/why to respond
        """
        if not self.config.check_submissions:
            return TriggerCheckResult(
                should_respond=False,
                reason="Submission triggers are disabled",
            )

        # Handle both typed object and dict
        if isinstance(artifact, dict):
            submit_flag = artifact.get("submit", False)
            artifact_id = artifact.get("id", "")
            uploaded_by = artifact.get("uploaded_by_course_member_id")
            version_id = artifact.get("version_identifier")
            file_size = artifact.get("file_size", 0)
            uploaded_at = artifact.get("uploaded_at")
        else:
            submit_flag = artifact.submit if hasattr(artifact, "submit") else False
            artifact_id = artifact.id
            uploaded_by = artifact.uploaded_by_course_member_id if hasattr(artifact, "uploaded_by_course_member_id") else None
            version_id = artifact.version_identifier if hasattr(artifact, "version_identifier") else None
            file_size = artifact.file_size if hasattr(artifact, "file_size") else 0
            uploaded_at = artifact.uploaded_at if hasattr(artifact, "uploaded_at") else None

        # Check if this is an official submission
        if not submit_flag:
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
                response_tag in (m.title or "")
                for m in existing_responses
            )

            if has_response:
                return TriggerCheckResult(
                    should_respond=False,
                    reason=f"Already responded to submission (found #{response_tag} tag)",
                )
        except Exception as e:
            logger.warning(f"Could not check for existing responses: {e}")

        return TriggerCheckResult(
            should_respond=True,
            reason="New submission artifact with submit=True",
            submission_trigger=SubmissionTrigger(
                artifact_id=artifact_id,
                submission_group_id=submission_group_id,
                uploaded_by_course_member_id=uploaded_by,
                version_identifier=version_id,
                file_size=file_size,
                uploaded_at=uploaded_at,
            ),
        )

    async def _get_course_member_by_user_id(
        self, user_id: str, course_id: str
    ) -> Optional[CourseMemberList]:
        """Get course member by user_id and course_id."""
        if not user_id or not course_id:
            return None

        cache_key = f"{user_id}:{course_id}"
        if cache_key in self._role_cache:
            # Note: cache stores role string, not full course_member
            # For full object, we need to fetch anyway
            pass

        try:
            members = await self.course_members.list(
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
