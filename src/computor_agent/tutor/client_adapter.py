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

    ComputorClient uses:
    - submission_groups.get(id=...)
    - submission_groups.list(course_id=...)
    - messages.list(submission_group_id=...)
    - messages.create(data=...)
    - course_members.list(user_id=..., course_id=...)
    - course_contents.get(id=...)

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
            sg = await self._client.submission_groups.get(id=submission_group_id)
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
            sg = await self._client.submission_groups.get(id=submission_group_id)
            course_id = sg.course_id if hasattr(sg, "course_id") else sg.get("course_id")

            if not course_id:
                return []

            # Get submission group members
            members_info = []
            sg_members = await self._client.submission_group_members.list(
                submission_group_id=submission_group_id,
            )

            # Get course member details for each submission group member
            for sgm in sg_members:
                course_member_id = (
                    sgm.course_member_id if hasattr(sgm, "course_member_id")
                    else sgm.get("course_member_id")
                )
                if course_member_id:
                    try:
                        cm = await self._client.course_members.get(id=course_member_id)
                        if cm:
                            members_info.append(
                                cm.model_dump() if hasattr(cm, "model_dump") else dict(cm)
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
            comments = await self._client.course_member_comments.list(
                course_member_id=course_member_id,
            )
            return [
                c.model_dump() if hasattr(c, "model_dump") else dict(c)
                for c in comments
            ]
        except Exception as e:
            logger.warning(f"Failed to get comments for {course_member_id}: {e}")
            return []

    async def get_course_content(self, course_content_id: str) -> dict:
        """Get course content (assignment) details."""
        try:
            cc = await self._client.course_contents.get(id=course_content_id)
            return cc.model_dump() if hasattr(cc, "model_dump") else dict(cc)
        except Exception as e:
            logger.warning(f"Failed to get course content {course_content_id}: {e}")
            return {}

    async def create_message(
        self,
        submission_group_id: str,
        content: str,
        title: str = "",
        parent_id: Optional[str] = None,
    ) -> dict:
        """
        Create a message in a submission group.

        Args:
            submission_group_id: The submission group ID
            content: Message content
            title: Message title (can include tags like #ai::response)
            parent_id: ID of message to reply to (creates message chain)

        Returns:
            The created message as a dict
        """
        try:
            data = {
                "submission_group_id": submission_group_id,
                "content": content,
                "title": title,
            }
            if parent_id:
                data["parent_id"] = parent_id

            message = await self._client.messages.create(data=data)
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

            result = await self._client.submission_groups.update(
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

    # =========================================================================
    # Tutor Endpoints (Aggregated Data)
    # =========================================================================

    async def get_ungraded_submission_groups(
        self,
        course_id: Optional[str] = None,
        course_content_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict]:
        """
        Get submission groups that have ungraded submissions.

        Uses: GET /tutors/submission-groups?has_ungraded_submissions=true

        Args:
            course_id: Optional filter by course
            course_content_id: Optional filter by course content
            limit: Maximum number of results

        Returns:
            List of submission groups with ungraded work
        """
        try:
            kwargs = {
                "has_ungraded_submissions": True,
                "limit": limit,
            }
            if course_id:
                kwargs["course_id"] = course_id
            if course_content_id:
                kwargs["course_content_id"] = course_content_id

            groups = await self._client.tutors.get_submission_groups(**kwargs)
            return [
                g.model_dump() if hasattr(g, "model_dump") else dict(g)
                for g in groups
            ]
        except Exception as e:
            logger.warning(f"Failed to get ungraded submission groups: {e}")
            return []

    async def get_tutor_submission_group(self, submission_group_id: str) -> dict:
        """
        Get detailed submission group info via tutor endpoint.

        Uses: GET /tutors/submission-groups/{id}

        Returns submission group with:
        - members (with names, emails)
        - grading_statistics (has_ungraded, latest_grade, average_grade)
        - latest_submission_id
        - submission_count, test_run_count
        """
        try:
            sg = await self._client.tutors.submission_groups(submission_group_id)
            return sg.model_dump() if hasattr(sg, "model_dump") else dict(sg)
        except Exception as e:
            logger.warning(f"Failed to get tutor submission group {submission_group_id}: {e}")
            return {}

    async def get_student_course_content(
        self,
        course_member_id: str,
        course_content_id: str,
    ) -> dict:
        """
        Get student's work and test results for a course content.

        Uses: GET /tutors/course-members/{cm_id}/course-contents/{cc_id}

        Returns:
        - result.result (test score float 0-1)
        - result.result_json (detailed test output)
        - submission_group with gradings history
        - submitted status
        """
        try:
            content = await self._client.tutors.get_course_members_course_contents(
                course_member_id=course_member_id,
                course_content_id=course_content_id,
            )
            return content.model_dump() if hasattr(content, "model_dump") else dict(content)
        except Exception as e:
            logger.warning(
                f"Failed to get student course content cm={course_member_id} cc={course_content_id}: {e}"
            )
            return {}

    async def submit_tutor_grade(
        self,
        course_member_id: str,
        course_content_id: str,
        grade: float,
        status: int,
        feedback: str,
        artifact_id: Optional[str] = None,
    ) -> dict:
        """
        Submit a grade via the tutors endpoint.

        Uses: PATCH /tutors/course-members/{cm_id}/course-contents/{cc_id}

        Args:
            course_member_id: The student's course member ID
            course_content_id: The assignment/course content ID
            grade: Grade value 0.0-1.0
            status: GradingStatus (0=NOT_REVIEWED, 1=CORRECTED, 2=CORRECTION_NECESSARY, 3=IMPROVEMENT_POSSIBLE)
            feedback: Feedback/comment for the student
            artifact_id: Specific artifact to grade (optional, defaults to latest)

        Returns:
            Response with graded_artifact_id and graded_artifact_info
        """
        try:
            data = {
                "grade": grade,
                "status": status,
                "feedback": feedback,
            }
            if artifact_id:
                data["artifact_id"] = artifact_id

            result = await self._client.tutors.course_members_course_contents(
                course_member_id=course_member_id,
                course_content_id=course_content_id,
                data=data,
            )
            return result.model_dump() if hasattr(result, "model_dump") else dict(result)
        except Exception as e:
            logger.error(
                f"Failed to submit grade cm={course_member_id} cc={course_content_id}: {e}"
            )
            raise

    async def get_tutor_courses(self) -> list[dict]:
        """
        Get all courses the tutor can access.

        Uses: GET /tutors/courses
        """
        try:
            courses = await self._client.tutors.get_courses()
            return [
                c.model_dump() if hasattr(c, "model_dump") else dict(c)
                for c in courses
            ]
        except Exception as e:
            logger.warning(f"Failed to get tutor courses: {e}")
            return []

    async def get_tutor_course_members(
        self,
        course_id: Optional[str] = None,
    ) -> list[dict]:
        """
        Get course members with grading statistics.

        Uses: GET /tutors/course-members

        Returns members with:
        - ungraded_submissions_count
        - unread_message_count
        """
        try:
            kwargs = {}
            if course_id:
                kwargs["course_id"] = course_id

            members = await self._client.tutors.get_course_members(**kwargs)
            return [
                m.model_dump() if hasattr(m, "model_dump") else dict(m)
                for m in members
            ]
        except Exception as e:
            logger.warning(f"Failed to get tutor course members: {e}")
            return []

    async def download_reference(
        self,
        course_content_id: str,
        output_path: str,
        with_dependencies: bool = False,
    ) -> bool:
        """
        Download reference solution as ZIP.

        Uses: GET /tutors/course-contents/{cc_id}/reference

        Args:
            course_content_id: The course content ID
            output_path: Path to save the ZIP file
            with_dependencies: Include dependent content

        Returns:
            True if successful, False otherwise
        """
        try:
            # This endpoint returns a ZIP file
            response = await self._client.tutors.get_course_contents_reference(
                course_content_id=course_content_id,
                with_dependencies=with_dependencies,
            )

            # Write the ZIP content to file
            with open(output_path, "wb") as f:
                if hasattr(response, "content"):
                    f.write(response.content)
                elif isinstance(response, bytes):
                    f.write(response)
                else:
                    logger.warning(f"Unexpected response type for reference download: {type(response)}")
                    return False

            return True
        except Exception as e:
            logger.warning(f"Failed to download reference for {course_content_id}: {e}")
            return False
