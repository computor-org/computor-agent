"""
Scheduler for the Tutor AI Agent.

Polls for:
1. Course members with ungraded submissions (ungraded_submissions_count > 0)
2. Course members with unread messages (unread_message_count > 0)

The scheduler is configurable and calls the TutorAgent when triggers are detected.
Tag-based trigger detection uses the TriggerConfig from tutor config.

Efficient API flow (minimal calls):
1. GET /tutors/course-members?course_id=...
   → Get list with ungraded_submissions_count and unread_message_count
2. GET /tutors/course-members/{cm_id}
   → Get unreviewed_course_contents list for members needing attention
3. GET /tutors/course-members/{cm_id}/course-contents/{cc_id}
   → Get full details (test results, gradings, submission_group) for processing
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
from computor_types.student_course_contents import (
    CourseContentStudentGet,
    CourseContentStudentList,
)
from computor_types.tutor_course_members import TutorCourseMemberList

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
                    course_content: CourseContentStudentGet
                ) -> None
            on_submission_trigger: Async callback when submission trigger detected
                Signature: async def callback(
                    trigger: TriggerCheckResult,
                    course_content: CourseContentStudentGet
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
        """
        Perform one polling cycle using efficient course-member based approach.

        Flow:
        1. GET /tutors/course-members → Get all members with counts
        2. Filter to members with ungraded_submissions_count > 0 or unread_message_count > 0
        3. For each, GET /tutors/course-members/{cm_id} → Get unreviewed_course_contents
        4. For each course content, GET details and process
        """
        tasks = []

        # =====================================================================
        # Get course members that need attention (single API call per course)
        # =====================================================================
        try:
            # Get all course members the tutor can see
            # TutorCourseMemberList has: ungraded_submissions_count, unread_message_count
            members = await self._get_all_course_members()

            if not members:
                logger.debug("No course members found")
                return

            # Filter to members needing attention
            members_needing_attention = []
            for member in members:
                needs_submission_check = (
                    self.config.check_submissions
                    and self.on_submission_trigger
                    and (member.ungraded_submissions_count or 0) > 0
                )
                needs_message_check = (
                    self.config.check_messages
                    and self.on_message_trigger
                    and (member.unread_message_count or 0) > 0
                )

                # Skip staff members (tutors, lecturers)
                if member.course_role_id in STAFF_ROLES:
                    continue

                if needs_submission_check or needs_message_check:
                    members_needing_attention.append(member)

            logger.debug(
                f"Found {len(members_needing_attention)} members needing attention "
                f"(out of {len(members)} total)"
            )

            # Process each member needing attention
            for member in members_needing_attention:
                # Check cooldown using course_member_id
                if self._should_skip(member.id, check_type="any"):
                    continue

                tasks.append(self._process_course_member(member))

        except Exception as e:
            logger.warning(f"Error in course member polling: {e}")

        # Run all checks concurrently (limited by semaphore)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _process_course_member(self, member: TutorCourseMemberList) -> None:
        """
        Process a course member that needs attention.

        Gets course contents list and processes those needing attention.
        Only fetches detailed content for items that actually need processing.
        """
        async with self._semaphore:
            try:
                # Get all course contents for this member (single API call)
                # GET /tutors/course-members/{cm_id}/course-contents
                course_contents = await self._get_course_member_contents_list(member.id)
                if not course_contents:
                    return

                # Filter to course contents that need attention
                for cc in course_contents:
                    needs_attention = False

                    # Check for ungraded submissions
                    # SubmissionGroupStudentList has: count (submissions), grading (latest grade float)
                    # If count > 0 and status is not "corrected", it may need grading
                    if self.config.check_submissions and self.on_submission_trigger:
                        sg = cc.submission_group
                        if sg and sg.count and sg.count > 0:
                            # Has submissions - if status is not set or not "corrected", needs attention
                            if sg.status is None or sg.status not in ("corrected", "improvement_possible"):
                                needs_attention = True

                    # Check for unread messages
                    if self.config.check_messages and self.on_message_trigger:
                        if cc.unread_message_count > 0:
                            needs_attention = True

                    if not needs_attention:
                        continue

                    # Check cooldown using submission_group_id if available
                    sg = cc.submission_group
                    if sg and sg.id and self._should_skip(sg.id, check_type="any"):
                        continue

                    # Get full course content details for processing
                    # GET /tutors/course-members/{cm_id}/course-contents/{cc_id}
                    content = await self._get_course_member_content(member.id, cc.id)
                    if not content:
                        continue

                    # Process the course content
                    await self._process_course_content(member, content)

            except Exception as e:
                logger.warning(f"Error processing course member {member.id}: {e}")

    async def _process_course_content(
        self,
        member: TutorCourseMemberList,
        content: CourseContentStudentGet,
    ) -> None:
        """
        Process a course content that needs attention.

        Determines if it's a submission trigger or message trigger and calls
        the appropriate callback.
        """
        sg = content.submission_group
        if not sg:
            return

        submission_group_id = sg.id
        if not submission_group_id:
            return

        state = self._get_or_create_state(submission_group_id)
        if state.processing:
            return

        state.processing = True
        try:
            # Check for submission trigger (ungraded submission)
            needs_grading, artifact_id = self._needs_grading(content)
            if needs_grading and self.on_submission_trigger:
                # Get latest artifact ID if not already known
                if not artifact_id:
                    # Use submission count or gradings to infer
                    artifact_id = f"submission-{submission_group_id}"

                # Check if already processed
                if artifact_id not in self._processed_artifacts:
                    result = TriggerCheckResult(
                        should_respond=True,
                        reason=f"Ungraded submission for {member.user.given_name} {member.user.family_name}",
                        submission_trigger=SubmissionTrigger(
                            artifact_id=artifact_id,
                            submission_group_id=submission_group_id,
                            uploaded_by_course_member_id=member.id,
                            version_identifier=None,
                            file_size=0,
                            uploaded_at=None,
                        ),
                    )

                    logger.info(
                        f"Submission trigger for {member.id} on {content.id}: "
                        f"artifact={artifact_id}"
                    )

                    # Pass full content data to callback for context
                    await self.on_submission_trigger(result, content)

                    self._processed_artifacts.add(artifact_id)
                    state.last_artifact_id = artifact_id
                    state.last_processed = datetime.now()

            # Check for message trigger (unread messages)
            if content.unread_message_count > 0 and self.on_message_trigger:
                # Use trigger checker to get message details
                result = await self._trigger_checker.check_message_trigger(
                    submission_group_id,
                    member.course_id,
                )

                if result.should_respond and result.message_trigger:
                    if state.last_message_id != result.message_trigger.message_id:
                        logger.info(
                            f"Message trigger for {member.id} on {content.id}: "
                            f"{result.reason}"
                        )

                        # Create a minimal submission group object for callback
                        await self.on_message_trigger(result, content)

                        state.last_message_id = result.message_trigger.message_id
                        state.last_processed = datetime.now()

        finally:
            state.processing = False

    async def _get_all_course_members(self) -> list[TutorCourseMemberList]:
        """
        Get all course members the tutor can see.

        Uses: GET /tutors/course-members
        Returns: List of TutorCourseMemberList with counts
        """
        try:
            return await self.client.tutors.get_course_members()
        except Exception as e:
            logger.error(f"Failed to get course members: {e}")
            return []

    async def _get_course_member_contents_list(
        self, course_member_id: str
    ) -> list[CourseContentStudentList]:
        """
        Get all course contents for a course member (list view).

        Uses: GET /tutors/course-members/{cm_id}/course-contents
        Returns: List of CourseContentStudentList with basic info
        """
        try:
            # Note: method has typo in name (get_urse_member_id_course_contents)
            return await self.client.tutors.get_urse_member_id_course_contents(course_member_id)
        except Exception as e:
            logger.warning(f"Failed to get course contents list for {course_member_id}: {e}")
            return []

    # =========================================================================
    # Course Member Content Methods (with caching)
    # =========================================================================

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

    def _should_skip(self, identifier: str, check_type: str = "any") -> bool:
        """
        Check if an identifier (course_member_id or submission_group_id) should be skipped due to cooldown.

        Args:
            identifier: The identifier to check (course_member_id or submission_group_id)
            check_type: Type of check ("message", "submission", or "any")
        """
        state = self._states.get(identifier)

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
