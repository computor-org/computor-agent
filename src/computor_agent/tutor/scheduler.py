"""
Scheduler for the Tutor AI Agent.

Polls for:
1. Submission groups with messages tagged with request tags (e.g., #ai::request)
2. Ungraded submissions via tutor endpoint (has_ungraded_submissions=true)

The scheduler is configurable and calls the TutorAgent when triggers are detected.
Tag-based trigger detection uses the TriggerConfig from tutor config.

Key endpoints used:
- GET /tutors/submission-groups?has_ungraded_submissions=true
- GET /tutors/submission-groups/{id} for details
- GET /messages?tags=...&unread=true for message triggers
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Generic, Optional, Protocol, Set, TypeVar, Union

from pydantic import BaseModel, Field

# Import API types from computor-types (source of truth)
from computor_types.grading import GradingStatus
from computor_types.student_course_contents import CourseContentStudentGet
from computor_types.submission_groups import SubmissionGroupList
from computor_types.tutor_course_members import TutorCourseMemberList
from computor_types.tutor_submission_groups import (
    TutorSubmissionGroupGet,
    TutorSubmissionGroupList,
)

from computor_agent.tutor.config import TriggerConfig
from computor_agent.tutor.trigger import (
    TriggerChecker,
    TriggerCheckResult,
    SubmissionTrigger,
    STAFF_ROLES,
)

# Type variable for generic cache entries
T = TypeVar("T")

logger = logging.getLogger(__name__)


class CacheConfig(BaseModel):
    """Configuration for data caching."""

    enabled: bool = Field(
        default=True,
        description="Enable caching of course member data",
    )
    course_members_ttl_seconds: int = Field(
        default=10800,  # 3 hours
        ge=60,
        le=86400,
        description="How long to cache course member list (seconds)",
    )
    course_content_ttl_seconds: int = Field(
        default=300,  # 5 minutes
        ge=30,
        le=3600,
        description="How long to cache course content details (seconds)",
    )
    persist_to_file: bool = Field(
        default=False,
        description="Persist cache to file for restart survival",
    )
    cache_dir: Optional[Path] = Field(
        default=None,
        description="Directory for cache files (default: ~/.computor/cache)",
    )

    def get_cache_dir(self) -> Path:
        """Get cache directory path."""
        if self.cache_dir:
            return Path(self.cache_dir).expanduser().resolve()
        return Path("~/.computor/cache").expanduser().resolve()


class SchedulerConfig(BaseModel):
    """Configuration for the tutor scheduler."""

    enabled: bool = Field(
        default=True,
        description="Enable the scheduler",
    )
    poll_interval_seconds: int = Field(
        default=30,
        ge=5,
        le=3600,
        description="How often to poll for new triggers (seconds)",
    )
    max_concurrent_processing: int = Field(
        default=5,
        ge=1,
        le=50,
        description="Maximum concurrent submission groups being processed",
    )
    cooldown_seconds: int = Field(
        default=60,
        ge=0,
        description="Minimum seconds between processing the same submission group",
    )
    check_messages: bool = Field(
        default=True,
        description="Check for unanswered student messages",
    )
    check_submissions: bool = Field(
        default=True,
        description="Check for new submissions with submit=True",
    )
    cache: CacheConfig = Field(
        default_factory=CacheConfig,
        description="Cache configuration for reducing API calls",
    )


@dataclass
class ProcessingState:
    """Tracks processing state for a submission group."""

    submission_group_id: str
    last_processed: Optional[datetime] = None
    processing: bool = False
    last_message_id: Optional[str] = None
    last_artifact_id: Optional[str] = None


@dataclass
class CacheEntry(Generic[T]):
    """Generic cache entry with timestamp and typed data."""

    data: T
    fetched_at: datetime = field(default_factory=datetime.now)


class TutorCache:
    """
    Cache for tutor API data to reduce API calls.

    Caches the actual API response types from computor-types:
    - list[TutorCourseMemberList] from GET /tutors/course-members
    - CourseContentStudentGet from GET /tutors/course-members/{id}/course-contents/{id}

    TTL-based invalidation with configurable durations.
    """

    def __init__(self, config: CacheConfig) -> None:
        self.config = config
        # course_id -> CacheEntry containing list of TutorCourseMemberList
        self._course_members: dict[str, CacheEntry[list[TutorCourseMemberList]]] = {}
        # f"{course_member_id}:{course_content_id}" -> CacheEntry containing CourseContentStudentGet
        self._course_contents: dict[str, CacheEntry[CourseContentStudentGet]] = {}

    def _is_stale(self, entry: Optional[CacheEntry], ttl_seconds: int) -> bool:
        """Check if a cache entry is stale."""
        if not self.config.enabled or entry is None:
            return True
        ttl = timedelta(seconds=ttl_seconds)
        return datetime.now() - entry.fetched_at > ttl

    def get_course_members(self, course_id: str) -> Optional[list[TutorCourseMemberList]]:
        """
        Get cached course members if not stale.

        Returns:
            List of TutorCourseMemberList objects, or None if stale/missing
        """
        entry = self._course_members.get(course_id)
        if self._is_stale(entry, self.config.course_members_ttl_seconds):
            return None
        return entry.data if entry else None

    def set_course_members(self, course_id: str, members: list[TutorCourseMemberList]) -> None:
        """
        Cache course members.

        Args:
            course_id: Course ID
            members: List of TutorCourseMemberList from GET /tutors/course-members
        """
        self._course_members[course_id] = CacheEntry(data=members)

    def get_course_content(
        self, course_member_id: str, course_content_id: str
    ) -> Optional[CourseContentStudentGet]:
        """
        Get cached course content if not stale.

        Returns:
            CourseContentStudentGet object, or None if stale/missing
        """
        key = f"{course_member_id}:{course_content_id}"
        entry = self._course_contents.get(key)
        if self._is_stale(entry, self.config.course_content_ttl_seconds):
            return None
        return entry.data if entry else None

    def set_course_content(
        self, course_member_id: str, course_content_id: str, content: CourseContentStudentGet
    ) -> None:
        """
        Cache course content.

        Args:
            course_member_id: Course member ID
            course_content_id: Course content ID
            content: CourseContentStudentGet from GET /tutors/course-members/{id}/course-contents/{id}
        """
        key = f"{course_member_id}:{course_content_id}"
        self._course_contents[key] = CacheEntry(data=content)

    def invalidate_course_content(self, course_member_id: str, course_content_id: str) -> None:
        """Invalidate specific course content cache entry."""
        key = f"{course_member_id}:{course_content_id}"
        self._course_contents.pop(key, None)

    def invalidate_course_members(self, course_id: str) -> None:
        """Invalidate course members cache for a course."""
        self._course_members.pop(course_id, None)

    def clear(self) -> None:
        """Clear all cached data."""
        self._course_members.clear()
        self._course_contents.clear()

    def get_stats(self) -> dict:
        """Get cache statistics."""
        return {
            "courses_cached": len(self._course_members),
            "total_members_cached": sum(
                len(e.data) for e in self._course_members.values() if e.data
            ),
            "course_contents_cached": len(self._course_contents),
            "config": {
                "enabled": self.config.enabled,
                "course_members_ttl": self.config.course_members_ttl_seconds,
                "course_content_ttl": self.config.course_content_ttl_seconds,
            },
        }


class ComputorClientProtocol(Protocol):
    """Protocol for Computor API client with required endpoints."""

    @property
    def messages(self): ...

    @property
    def course_members(self): ...

    @property
    def submission_groups(self): ...

    @property
    def submissions(self): ...

    @property
    def tutors(self): ...


class TutorScheduler:
    """
    Scheduler that polls for tutor triggers and invokes processing.

    The scheduler:
    1. Polls submission groups for messages with configured request tags
    2. Polls for new submission artifacts with submit=True
    3. Invokes a callback when triggers are detected
    4. Manages cooldowns and concurrent processing limits

    Usage:
        trigger_config = TriggerConfig(
            request_tags=[TriggerTag(scope="ai", value="request")],
            response_tag=TriggerTag(scope="ai", value="response"),
        )
        scheduler = TutorScheduler(
            client=computor_client,
            config=scheduler_config,
            trigger_config=trigger_config,
            on_message_trigger=handle_message,
            on_submission_trigger=handle_submission,
        )

        # Start polling
        await scheduler.start()

        # Stop polling
        await scheduler.stop()
    """

    def __init__(
        self,
        client: ComputorClientProtocol,
        config: SchedulerConfig,
        trigger_config: Optional[TriggerConfig] = None,
        on_message_trigger: Optional[Callable] = None,
        on_submission_trigger: Optional[Callable] = None,
    ) -> None:
        """
        Initialize the scheduler.

        Args:
            client: Computor API client
            config: Scheduler configuration
            trigger_config: Tag-based trigger configuration (uses defaults if not provided)
            on_message_trigger: Async callback when message trigger detected
                Signature: async def callback(
                    trigger: TriggerCheckResult,
                    submission_group: SubmissionGroupList
                ) -> None
            on_submission_trigger: Async callback when submission trigger detected
                Signature: async def callback(
                    trigger: TriggerCheckResult,
                    submission_group: TutorSubmissionGroupGet
                ) -> None
        """
        self.client = client
        self.config = config
        self.trigger_config = trigger_config or TriggerConfig()
        self.on_message_trigger = on_message_trigger
        self.on_submission_trigger = on_submission_trigger

        self._trigger_checker = TriggerChecker(
            messages_client=client.messages,
            course_members_client=client.course_members,
            config=self.trigger_config,
        )

        # Cache for reducing API calls
        self._cache = TutorCache(config.cache)

        # State tracking
        self._states: dict[str, ProcessingState] = {}
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._semaphore: Optional[asyncio.Semaphore] = None

        # Track processed artifacts to avoid duplicates
        self._processed_artifacts: Set[str] = set()

    async def start(self) -> None:
        """Start the scheduler polling loop."""
        if self._running:
            logger.warning("Scheduler already running")
            return

        if not self.config.enabled:
            logger.info("Scheduler is disabled")
            return

        logger.info(
            f"Starting tutor scheduler (poll_interval={self.config.poll_interval_seconds}s)"
        )

        self._running = True
        self._semaphore = asyncio.Semaphore(self.config.max_concurrent_processing)
        self._task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        """Stop the scheduler polling loop."""
        if not self._running:
            return

        logger.info("Stopping tutor scheduler")
        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _poll_loop(self) -> None:
        """Main polling loop."""
        while self._running:
            try:
                await self._poll_once()
            except Exception as e:
                logger.exception(f"Error in poll loop: {e}")

            await asyncio.sleep(self.config.poll_interval_seconds)

    async def _poll_once(self) -> None:
        """Perform one polling cycle."""
        tasks = []

        # =====================================================================
        # 1. Check for ungraded submissions via tutor endpoint
        # =====================================================================
        if self.config.check_submissions and self.on_submission_trigger:
            try:
                ungraded_groups = await self._get_ungraded_submission_groups()
                logger.debug(f"Found {len(ungraded_groups)} groups with ungraded submissions")

                for sg in ungraded_groups:
                    # TutorSubmissionGroupList has .id attribute
                    if not sg.id:
                        continue

                    # Check if we should skip due to cooldown
                    if self._should_skip(sg.id, check_type="submission"):
                        continue

                    tasks.append(self._process_ungraded_submission(sg))
            except Exception as e:
                logger.warning(f"Error checking ungraded submissions: {e}")

        # =====================================================================
        # 2. Check for message triggers (tag-based)
        # =====================================================================
        if self.config.check_messages and self.on_message_trigger:
            submission_groups = await self._get_submission_groups()
            logger.debug(f"Checking {len(submission_groups)} submission groups for messages")

            for sg in submission_groups:
                # SubmissionGroupList has .id and .course_id attributes
                if not sg.id or not sg.course_id:
                    continue

                # Check if we should skip due to cooldown
                if self._should_skip(sg.id, check_type="message"):
                    continue

                # Create check task for message triggers
                tasks.append(self._check_message_trigger(sg.id, sg.course_id, sg))

        # Run all checks concurrently (limited by semaphore)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _check_message_trigger(
        self,
        submission_group_id: str,
        course_id: str,
        submission_group: SubmissionGroupList,
    ) -> None:
        """Check for message triggers (tag-based) and process if needed."""
        async with self._semaphore:
            state = self._get_or_create_state(submission_group_id)

            if state.processing:
                return

            state.processing = True

            try:
                result = await self._trigger_checker.check_message_trigger(
                    submission_group_id,
                    course_id,
                )

                if result.should_respond and result.message_trigger:
                    # Check if this message was already processed
                    if state.last_message_id != result.message_trigger.message_id:
                        logger.info(
                            f"Message trigger for {submission_group_id}: "
                            f"{result.reason}"
                        )

                        await self.on_message_trigger(result, submission_group)

                        state.last_message_id = result.message_trigger.message_id
                        state.last_processed = datetime.now()

            finally:
                state.processing = False

    async def _process_ungraded_submission(
        self, submission_group: TutorSubmissionGroupList
    ) -> None:
        """
        Process an ungraded submission detected via tutor endpoint.

        This uses the tutor endpoints which provide pre-filtered data:
        - GET /tutors/submission-groups?has_ungraded_submissions=true
        - GET /tutors/submission-groups/{id} for details

        Args:
            submission_group: TutorSubmissionGroupList from the list endpoint
        """
        async with self._semaphore:
            sg_id = submission_group.id
            if not sg_id:
                return

            state = self._get_or_create_state(sg_id)

            if state.processing:
                return

            state.processing = True

            try:
                # Get detailed info from tutor endpoint
                sg_details = await self._get_tutor_submission_group_details(sg_id)
                if not sg_details:
                    return

                # Extract key info from TutorSubmissionGroupGet
                course_content_id = sg_details.course_content_id
                course_id = sg_details.course_id
                latest_submission_id = sg_details.latest_submission_id
                members = sg_details.members  # List[TutorSubmissionGroupMember]

                # Skip if no submission or already processed
                if not latest_submission_id:
                    return

                if latest_submission_id in self._processed_artifacts:
                    return

                # Build trigger result
                result = TriggerCheckResult(
                    should_respond=True,
                    reason="Ungraded submission detected (has_ungraded_submissions=true)",
                    submission_trigger=SubmissionTrigger(
                        artifact_id=latest_submission_id,
                        submission_group_id=sg_id,
                        uploaded_by_course_member_id=members[0].course_member_id if members else None,
                        version_identifier=None,
                        file_size=0,
                        uploaded_at=sg_details.latest_submission_at,
                    ),
                )

                logger.info(
                    f"Ungraded submission for {sg_id}: "
                    f"artifact={latest_submission_id}, "
                    f"course_content={course_content_id}"
                )

                # Call the callback with the detailed submission group data
                await self.on_submission_trigger(result, sg_details)

                self._processed_artifacts.add(latest_submission_id)
                state.last_artifact_id = latest_submission_id
                state.last_processed = datetime.now()

            except Exception as e:
                logger.warning(f"Error processing ungraded submission {sg_id}: {e}")

            finally:
                state.processing = False

    # =========================================================================
    # Course Member Based Methods (with caching)
    # =========================================================================

    async def _get_course_members(self, course_id: str) -> list[TutorCourseMemberList]:
        """
        Get course members for a course, using cache if available.

        Uses: GET /tutors/course-members?course_id={course_id}
        Returns: List of TutorCourseMemberList objects
        """
        # Check cache first
        cached = self._cache.get_course_members(course_id)
        if cached is not None:
            logger.debug(f"Using cached course members for {course_id} ({len(cached)} members)")
            return cached

        # Fetch from API
        try:
            members = await self.client.tutors.get_course_members(course_id=course_id)
            self._cache.set_course_members(course_id, members)
            logger.debug(f"Fetched and cached {len(members)} course members for {course_id}")
            return members
        except Exception as e:
            logger.error(f"Failed to get course members for {course_id}: {e}")
            return []

    async def _get_course_member_content(
        self, course_member_id: str, course_content_id: str
    ) -> Optional[CourseContentStudentGet]:
        """
        Get detailed course content for a course member, using cache if available.

        Uses: GET /tutors/course-members/{course_member_id}/course-contents/{course_content_id}
        Returns: CourseContentStudentGet object or None
        """
        # Check cache first
        cached = self._cache.get_course_content(course_member_id, course_content_id)
        if cached is not None:
            logger.debug(f"Using cached course content for {course_member_id}:{course_content_id}")
            return cached

        # Fetch from API
        try:
            content = await self.client.tutors.get_course_members_course_contents(
                course_member_id, course_content_id
            )
            self._cache.set_course_content(course_member_id, course_content_id, content)
            logger.debug(f"Fetched and cached course content for {course_member_id}:{course_content_id}")
            return content
        except Exception as e:
            logger.warning(f"Failed to get course content {course_member_id}:{course_content_id}: {e}")
            return None

    def _needs_grading(self, content: Optional[CourseContentStudentGet]) -> tuple[bool, Optional[str]]:
        """
        Determine if a course content needs grading based on its state.

        Args:
            content: CourseContentStudentGet object from computor-types

        Returns:
            Tuple of (needs_grading: bool, artifact_id: str or None)
        """
        if content is None:
            return False, None

        # Check if there's a submission group with submissions
        # CourseContentStudentGet.submission_group is Optional[SubmissionGroupStudentGet]
        sg = content.submission_group
        if sg is None:
            return False, None

        # Check submission count - SubmissionGroupStudentGet has 'count' field
        submission_count = sg.count if sg.count else content.submission_count
        if submission_count == 0:
            return False, None

        # Check if there are gradings - SubmissionGroupStudentGet.gradings is list[SubmissionGroupGradingList]
        gradings = sg.gradings if hasattr(sg, "gradings") and sg.gradings else []

        # If no gradings at all, needs grading
        if not gradings:
            return True, None

        # Check if the latest submission is graded
        # gradings are sorted by created_at, so the last one is the latest
        latest_grading = gradings[-1] if gradings else None

        # Compare submission count with grading count
        # If more submissions than gradings, needs grading
        if len(gradings) < submission_count:
            return True, None

        # Check grading status - if NOT_REVIEWED (0), needs grading
        if latest_grading:
            status = latest_grading.status
            if status is not None and status == GradingStatus.NOT_REVIEWED:
                return True, None

        return False, None

    async def _get_ungraded_submission_groups(self) -> list[TutorSubmissionGroupList]:
        """
        Get submission groups with ungraded submissions via tutor endpoint.

        Uses: GET /tutors/submission-groups?has_ungraded_submissions=true
        Returns: List of TutorSubmissionGroupList objects
        """
        try:
            groups = await self.client.tutors.get_submission_groups(
                has_ungraded_submissions=True,
            )
            return groups
        except Exception as e:
            logger.error(f"Failed to get ungraded submission groups: {e}")
            return []

    async def _get_tutor_submission_group_details(
        self, submission_group_id: str
    ) -> Optional[TutorSubmissionGroupGet]:
        """
        Get detailed submission group info via tutor endpoint.

        Uses: GET /tutors/submission-groups/{id}
        Returns: TutorSubmissionGroupGet object or None
        """
        try:
            return await self.client.tutors.submission_groups(submission_group_id)
        except Exception as e:
            logger.warning(f"Failed to get tutor submission group details {submission_group_id}: {e}")
            return None

    async def _get_submission_groups(self) -> list[SubmissionGroupList]:
        """
        Get submission groups to check for message triggers.

        Uses: GET /submission-groups
        Returns: List of SubmissionGroupList objects
        """
        try:
            return await self.client.submission_groups.list()
        except Exception as e:
            logger.error(f"Failed to get submission groups: {e}")
            return []

    def _should_skip(self, submission_group_id: str, check_type: str = "any") -> bool:
        """
        Check if a submission group should be skipped due to cooldown.

        Args:
            submission_group_id: The submission group to check
            check_type: Type of check ("message", "submission", or "any")
        """
        state = self._states.get(submission_group_id)

        if not state or not state.last_processed:
            return False

        cooldown = timedelta(seconds=self.config.cooldown_seconds)
        return datetime.now() - state.last_processed < cooldown

    def _get_or_create_state(self, submission_group_id: str) -> ProcessingState:
        """Get or create processing state for a submission group."""
        if submission_group_id not in self._states:
            self._states[submission_group_id] = ProcessingState(
                submission_group_id=submission_group_id
            )
        return self._states[submission_group_id]

    def get_stats(self) -> dict:
        """Get scheduler statistics."""
        return {
            "running": self._running,
            "tracked_groups": len(self._states),
            "processed_artifacts": len(self._processed_artifacts),
            "cache": self._cache.get_stats(),
            "config": self.config.model_dump(),
            "trigger_config": self.trigger_config.model_dump(),
        }

    def reset_state(self, submission_group_id: Optional[str] = None) -> None:
        """
        Reset processing state.

        Args:
            submission_group_id: Specific group to reset (None = all)
        """
        if submission_group_id:
            if submission_group_id in self._states:
                del self._states[submission_group_id]
        else:
            self._states.clear()
            self._processed_artifacts.clear()
            self._cache.clear()
