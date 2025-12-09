"""
Client adapters for the Tutor AI Agent.

Wraps the ComputorClient and LLM provider to provide the interface
expected by TutorAgent and ContextBuilder.
"""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class TutorLLMAdapter:
    """
    Adapts LLM provider to the interface expected by TutorAgent.

    The TutorAgent expects:
    - complete(prompt, system_prompt=...) -> str

    But LLMProvider has:
    - complete(prompt, system_prompt=...) -> LLMResponse

    This adapter extracts the content string from the response.
    """

    def __init__(self, llm_provider: Any) -> None:
        """
        Initialize the adapter.

        Args:
            llm_provider: LLMProvider instance
        """
        self._llm = llm_provider

    async def complete(
        self,
        prompt: str,
        *,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: float = 0.7,
    ) -> str:
        """Generate a completion and return just the content string."""
        response = await self._llm.complete(
            prompt,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        # Extract content from LLMResponse
        return response.content if hasattr(response, "content") else str(response)

    async def close(self) -> None:
        """Close the underlying LLM provider."""
        if hasattr(self._llm, "close"):
            await self._llm.close()


class TutorClientAdapter:
    """
    Adapts ComputorClient to the interface expected by TutorAgent.

    The TutorAgent expects methods like:
    - get_submission_group(submission_group_id)
    - get_messages(submission_group_id)
    - create_message(submission_group_id, content, title)

    But ComputorClient has:
    - submission_groups.get_submission_groups_id(id)
    - messages.list(submission_group_id=...)
    - messages.create(data)

    This adapter bridges the gap.
    """

    def __init__(self, client: Any) -> None:
        """
        Initialize the adapter.

        Args:
            client: ComputorClient instance
        """
        self._client = client

    async def get_submission_group(self, submission_group_id: str) -> dict:
        """Get submission group details."""
        try:
            sg = await self._client.submission_groups.get_submission_groups_id(
                id=submission_group_id,
            )
            return sg.model_dump() if hasattr(sg, "model_dump") else dict(sg)
        except Exception as e:
            logger.warning(f"Failed to get submission group {submission_group_id}: {e}")
            return {}

    async def get_messages(self, submission_group_id: str) -> list[dict]:
        """Get messages for a submission group."""
        try:
            messages = await self._client.messages.list(
                submission_group_id=submission_group_id,
            )
            return [
                m.model_dump() if hasattr(m, "model_dump") else dict(m)
                for m in messages
            ]
        except Exception as e:
            logger.warning(f"Failed to get messages for {submission_group_id}: {e}")
            return []

    async def get_course_members(self, submission_group_id: str) -> list[dict]:
        """Get course members for a submission group."""
        try:
            # First get the submission group to find the course_id
            sg = await self._client.submission_groups.get_submission_groups_id(
                id=submission_group_id,
            )
            course_id = sg.course_id if hasattr(sg, "course_id") else sg.get("course_id")

            if not course_id:
                return []

            # Get members associated with this submission group
            # The submission group should have member info
            members_info = []

            # Get course members for this submission group's members
            if hasattr(sg, "members") and sg.members:
                for member_id in sg.members:
                    try:
                        members = await self._client.course_members.get_course_members(
                            id=member_id,
                        )
                        if members:
                            m = members[0] if isinstance(members, list) else members
                            members_info.append(
                                m.model_dump() if hasattr(m, "model_dump") else dict(m)
                            )
                    except Exception:
                        pass

            return members_info
        except Exception as e:
            logger.warning(f"Failed to get course members for {submission_group_id}: {e}")
            return []

    async def get_course_member_comments(self, course_member_id: str) -> list[dict]:
        """Get comments for a course member."""
        try:
            # This may not be directly available in the API
            # Return empty for now
            return []
        except Exception as e:
            logger.warning(f"Failed to get comments for {course_member_id}: {e}")
            return []

    async def get_course_content(self, course_content_id: str) -> dict:
        """Get course content (assignment) details."""
        try:
            cc = await self._client.course_contents.get_course_contents_id(
                id=course_content_id,
            )
            return cc.model_dump() if hasattr(cc, "model_dump") else dict(cc)
        except Exception as e:
            logger.warning(f"Failed to get course content {course_content_id}: {e}")
            return {}

    async def create_message(
        self,
        submission_group_id: str,
        content: str,
        title: str = "",
    ) -> dict:
        """Create a message in a submission group."""
        try:
            message = await self._client.messages.create(
                data={
                    "submission_group_id": submission_group_id,
                    "content": content,
                    "title": title,
                },
            )
            return message.model_dump() if hasattr(message, "model_dump") else dict(message)
        except Exception as e:
            logger.error(f"Failed to create message in {submission_group_id}: {e}")
            raise

    async def update_submission_grading(
        self,
        submission_group_id: str,
        status: int,
        grade: Optional[float] = None,
        comment: Optional[str] = None,
    ) -> dict:
        """Update grading for a submission."""
        try:
            data = {"status": status}
            if grade is not None:
                data["grade"] = grade
            if comment is not None:
                data["comment"] = comment

            result = await self._client.submission_groups.patch_submission_groups(
                id=submission_group_id,
                data=data,
            )
            return result.model_dump() if hasattr(result, "model_dump") else dict(result)
        except Exception as e:
            logger.error(f"Failed to update grading for {submission_group_id}: {e}")
            raise

    async def mark_message_read(self, message_id: str) -> None:
        """Mark a message as read."""
        try:
            await self._client.messages.reads(id=message_id)
        except Exception as e:
            logger.warning(f"Failed to mark message {message_id} as read: {e}")
