"""
Progress Tracking Service for the Tutor AI Agent.

Fetches course and member progress metrics to provide
context-aware feedback based on overall student performance.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class ContentProgress:
    """
    Progress for a single course content item.

    Attributes:
        course_content_id: Content ID
        title: Content title
        path: Content path (e.g., "unit1.assignment1")
        result: Test result (0.0 to 1.0)
        grading: Tutor grade (0.0 to 1.0)
        status: Grading status
        submitted: Whether work was submitted
        has_unread_messages: Whether there are unread messages
    """
    course_content_id: str
    title: Optional[str] = None
    path: Optional[str] = None
    result: Optional[float] = None
    grading: Optional[float] = None
    status: Optional[str] = None
    submitted: bool = False
    has_unread_messages: bool = False

    @property
    def is_complete(self) -> bool:
        """Check if content is completed (submitted or graded)."""
        return self.submitted or self.grading is not None

    @property
    def is_passing(self) -> bool:
        """Check if tests are passing."""
        return self.result is not None and self.result >= 1.0


@dataclass
class MemberProgress:
    """
    Progress for a course member across all content.

    Attributes:
        course_member_id: Member ID
        course_id: Course ID
        display_name: Member's display name
        email: Member's email
        total_contents: Total number of content items
        completed_contents: Number of completed items
        submitted_contents: Number of submitted items
        passing_contents: Number of items with passing tests
        average_result: Average test result
        average_grading: Average tutor grade
        content_progress: Progress for each content item
    """
    course_member_id: str
    course_id: str
    display_name: Optional[str] = None
    email: Optional[str] = None
    total_contents: int = 0
    completed_contents: int = 0
    submitted_contents: int = 0
    passing_contents: int = 0
    average_result: Optional[float] = None
    average_grading: Optional[float] = None
    content_progress: list[ContentProgress] = field(default_factory=list)

    @property
    def completion_rate(self) -> float:
        """Get completion rate (0.0 to 1.0)."""
        if self.total_contents == 0:
            return 0.0
        return self.completed_contents / self.total_contents

    @property
    def pass_rate(self) -> float:
        """Get pass rate for submitted content (0.0 to 1.0)."""
        if self.submitted_contents == 0:
            return 0.0
        return self.passing_contents / self.submitted_contents

    def get_incomplete_contents(self) -> list[ContentProgress]:
        """Get list of incomplete content items."""
        return [c for c in self.content_progress if not c.is_complete]

    def get_failing_contents(self) -> list[ContentProgress]:
        """Get content items with failing tests."""
        return [
            c for c in self.content_progress
            if c.result is not None and c.result < 1.0
        ]

    def format_for_prompt(self) -> str:
        """Format progress for LLM prompt."""
        parts = [
            "=== Student Progress ===",
            f"Completion: {self.completion_rate:.0%} ({self.completed_contents}/{self.total_contents})",
        ]

        if self.average_result is not None:
            parts.append(f"Average Test Score: {self.average_result:.1%}")

        if self.average_grading is not None:
            parts.append(f"Average Grade: {self.average_grading:.1%}")

        incomplete = self.get_incomplete_contents()
        if incomplete:
            parts.append(f"\nIncomplete ({len(incomplete)}):")
            for c in incomplete[:5]:
                parts.append(f"  - {c.title or c.path}")

        failing = self.get_failing_contents()
        if failing:
            parts.append(f"\nNeeds Work ({len(failing)}):")
            for c in failing[:5]:
                result_str = f"{c.result:.0%}" if c.result else "N/A"
                parts.append(f"  - {c.title or c.path}: {result_str}")

        return "\n".join(parts)


@dataclass
class CourseProgress:
    """
    Overall progress for a course (aggregate across members).

    Attributes:
        course_id: Course ID
        course_title: Course title
        total_members: Total number of members
        total_contents: Total number of content items
        average_completion: Average completion rate
        average_result: Average test result
        members_with_issues: Number of members needing attention
    """
    course_id: str
    course_title: Optional[str] = None
    total_members: int = 0
    total_contents: int = 0
    average_completion: float = 0.0
    average_result: Optional[float] = None
    members_with_issues: int = 0

    def format_for_prompt(self) -> str:
        """Format course progress for LLM prompt."""
        parts = [
            f"=== Course Progress ({self.course_title or 'Unknown'}) ===",
            f"Members: {self.total_members}",
            f"Content Items: {self.total_contents}",
            f"Average Completion: {self.average_completion:.0%}",
        ]

        if self.average_result is not None:
            parts.append(f"Average Test Score: {self.average_result:.1%}")

        if self.members_with_issues > 0:
            parts.append(f"Members Needing Attention: {self.members_with_issues}")

        return "\n".join(parts)


class ProgressService:
    """
    Service for tracking course and member progress.

    Provides methods to:
    - Get progress for a specific member
    - Get overall course progress
    - Identify students needing attention
    - Generate progress-aware context for feedback

    Usage:
        service = ProgressService(client)

        # Get member progress
        progress = await service.get_member_progress(course_id, course_member_id)

        # Get progress summary for LLM
        summary = progress.format_for_prompt()

        # Get course overview
        course = await service.get_course_progress(course_id)
    """

    def __init__(self, client: Any) -> None:
        """
        Initialize the service.

        Args:
            client: ComputorClient instance
        """
        self.client = client

    async def get_member_progress(
        self,
        course_id: str,
        course_member_id: str,
    ) -> Optional[MemberProgress]:
        """
        Get progress for a specific course member.

        Args:
            course_id: Course ID
            course_member_id: Course member ID

        Returns:
            MemberProgress or None on failure
        """
        try:
            # Get course contents for this member via tutor endpoint
            contents = await self.client.tutors.course_members_course_contents_list(
                course_member_id=course_member_id,
            )

            if not contents:
                return MemberProgress(
                    course_member_id=course_member_id,
                    course_id=course_id,
                )

            # Build content progress
            content_progress = []
            results = []
            gradings = []
            submitted_count = 0
            passing_count = 0

            for c in contents:
                # Get result and grading
                result = None
                result_obj = getattr(c, "result", None)
                if result_obj:
                    result = getattr(result_obj, "result", None)

                grading = None
                status = None
                submitted = getattr(c, "submitted", False)

                sg = getattr(c, "submission_group", None)
                if sg:
                    grading = getattr(sg, "grading", None)
                    status = getattr(sg, "status", None)

                # Track aggregates
                if result is not None:
                    results.append(result)
                    if result >= 1.0:
                        passing_count += 1

                if grading is not None:
                    gradings.append(grading)

                if submitted:
                    submitted_count += 1

                content_progress.append(ContentProgress(
                    course_content_id=c.id,
                    title=getattr(c, "title", None),
                    path=getattr(c, "path", None),
                    result=result,
                    grading=grading,
                    status=status,
                    submitted=submitted,
                    has_unread_messages=getattr(c, "unread_message_count", 0) > 0,
                ))

            # Calculate averages
            avg_result = sum(results) / len(results) if results else None
            avg_grading = sum(gradings) / len(gradings) if gradings else None

            # Get member info
            member = await self._get_member_info(course_member_id)

            return MemberProgress(
                course_member_id=course_member_id,
                course_id=course_id,
                display_name=member.get("display_name"),
                email=member.get("email"),
                total_contents=len(content_progress),
                completed_contents=sum(1 for c in content_progress if c.is_complete),
                submitted_contents=submitted_count,
                passing_contents=passing_count,
                average_result=avg_result,
                average_grading=avg_grading,
                content_progress=content_progress,
            )

        except Exception as e:
            logger.warning(
                f"Failed to get progress for member {course_member_id}: {e}"
            )
            return None

    async def get_course_progress(
        self,
        course_id: str,
        *,
        group_id: Optional[str] = None,
    ) -> Optional[CourseProgress]:
        """
        Get overall progress for a course.

        Args:
            course_id: Course ID
            group_id: Optional group ID to filter by

        Returns:
            CourseProgress or None on failure
        """
        try:
            # Get course members
            members = await self.client.tutors.course_members_list(
                course_id=course_id,
                group_id=group_id,
            )

            if not members:
                return CourseProgress(course_id=course_id)

            # Get course info
            course = await self._get_course_info(course_id)

            total_members = len(members)
            completion_rates = []
            results = []
            members_with_issues = 0

            # Sample progress for a few members (for performance)
            sample_size = min(10, total_members)
            for member in members[:sample_size]:
                progress = await self.get_member_progress(course_id, member.id)
                if progress:
                    completion_rates.append(progress.completion_rate)
                    if progress.average_result is not None:
                        results.append(progress.average_result)
                    if progress.completion_rate < 0.5 or (
                        progress.average_result and progress.average_result < 0.5
                    ):
                        members_with_issues += 1

            # Scale up issues estimate
            if sample_size < total_members:
                members_with_issues = int(
                    members_with_issues * total_members / sample_size
                )

            return CourseProgress(
                course_id=course_id,
                course_title=course.get("title"),
                total_members=total_members,
                total_contents=course.get("content_count", 0),
                average_completion=(
                    sum(completion_rates) / len(completion_rates)
                    if completion_rates else 0.0
                ),
                average_result=(
                    sum(results) / len(results) if results else None
                ),
                members_with_issues=members_with_issues,
            )

        except Exception as e:
            logger.warning(f"Failed to get course progress for {course_id}: {e}")
            return None

    async def get_performance_context(
        self,
        course_id: str,
        course_member_id: str,
        course_content_id: str,
    ) -> dict[str, Any]:
        """
        Get performance context for generating personalized feedback.

        Args:
            course_id: Course ID
            course_member_id: Course member ID
            course_content_id: Current content ID

        Returns:
            Dict with performance context for LLM
        """
        progress = await self.get_member_progress(course_id, course_member_id)

        if not progress:
            return {"has_context": False}

        # Find current content
        current = None
        for c in progress.content_progress:
            if c.course_content_id == course_content_id:
                current = c
                break

        # Determine performance level
        if progress.average_result is not None:
            if progress.average_result >= 0.9:
                performance_level = "excellent"
            elif progress.average_result >= 0.7:
                performance_level = "good"
            elif progress.average_result >= 0.5:
                performance_level = "average"
            else:
                performance_level = "struggling"
        else:
            performance_level = "unknown"

        # Check if this is their first assignment
        is_first = progress.submitted_contents <= 1

        # Check for improvement trend
        improving = False
        recent_results = [
            c.result for c in progress.content_progress
            if c.result is not None
        ][-5:]
        if len(recent_results) >= 2:
            improving = recent_results[-1] > recent_results[0]

        return {
            "has_context": True,
            "performance_level": performance_level,
            "completion_rate": progress.completion_rate,
            "average_result": progress.average_result,
            "is_first_submission": is_first,
            "is_improving": improving,
            "incomplete_count": len(progress.get_incomplete_contents()),
            "failing_count": len(progress.get_failing_contents()),
            "current_content": {
                "title": current.title if current else None,
                "result": current.result if current else None,
                "grading": current.grading if current else None,
            } if current else None,
        }

    async def _get_member_info(self, course_member_id: str) -> dict[str, Any]:
        """Get basic member information."""
        try:
            member = await self.client.course_members.get(id=course_member_id)
            if member:
                return {
                    "display_name": getattr(member, "display_name", None),
                    "email": getattr(member, "email", None),
                }
        except Exception:
            pass
        return {}

    async def _get_course_info(self, course_id: str) -> dict[str, Any]:
        """Get basic course information."""
        try:
            course = await self.client.courses.get(id=course_id)
            if course:
                return {
                    "title": getattr(course, "title", None),
                    "content_count": getattr(course, "content_count", 0),
                }
        except Exception:
            pass
        return {}

    async def get_struggling_members(
        self,
        course_id: str,
        *,
        threshold: float = 0.5,
        limit: int = 10,
    ) -> list[MemberProgress]:
        """
        Get members who are struggling (below threshold).

        Args:
            course_id: Course ID
            threshold: Result threshold (members below this are struggling)
            limit: Maximum number of members to return

        Returns:
            List of struggling MemberProgress
        """
        try:
            members = await self.client.tutors.course_members_list(course_id=course_id)

            if not members:
                return []

            struggling = []
            for member in members:
                progress = await self.get_member_progress(course_id, member.id)
                if progress:
                    avg = progress.average_result
                    if avg is not None and avg < threshold:
                        struggling.append(progress)

                if len(struggling) >= limit:
                    break

            # Sort by average result (lowest first)
            struggling.sort(key=lambda p: p.average_result or 0)

            return struggling[:limit]

        except Exception as e:
            logger.warning(f"Failed to get struggling members: {e}")
            return []
