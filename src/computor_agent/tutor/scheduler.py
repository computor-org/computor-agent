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
from typing import Callable, Optional, Protocol, Set

from pydantic import BaseModel, Field

from computor_agent.tutor.config import TriggerConfig
from computor_agent.tutor.trigger import (
    TriggerChecker,
    TriggerCheckResult,
    SubmissionTrigger,
    STAFF_ROLES,
)

logger = logging.getLogger(__name__)


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
    course_content_ids: Optional[list[str]] = Field(
        default=None,
        description="Limit to specific course content IDs (None = all)",
    )
    course_ids: Optional[list[str]] = Field(
        default=None,
        description="Limit to specific course IDs (None = all)",
    )


@dataclass
class ProcessingState:
    """Tracks processing state for a submission group."""

    submission_group_id: str
    last_processed: Optional[datetime] = None
    processing: bool = False
    last_message_id: Optional[str] = None
    last_artifact_id: Optional[str] = None


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
                Signature: async def callback(trigger: TriggerCheckResult, submission_group: dict) -> None
            on_submission_trigger: Async callback when submission trigger detected
                Signature: async def callback(trigger: TriggerCheckResult, submission_group: dict) -> None
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
                    sg_id = sg.get("id") if isinstance(sg, dict) else getattr(sg, "id", None)
                    if not sg_id:
                        continue

                    # Check if we should skip due to cooldown
                    if self._should_skip(sg_id, check_type="submission"):
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
                sg_id = sg.id if hasattr(sg, "id") else sg.get("id")
                course_id = sg.course_id if hasattr(sg, "course_id") else sg.get("course_id")

                if not sg_id or not course_id:
                    continue

                # Check if we should skip due to cooldown
                if self._should_skip(sg_id, check_type="message"):
                    continue

                # Create check task for message triggers
                tasks.append(self._check_message_trigger(sg_id, course_id, sg))

        # Run all checks concurrently (limited by semaphore)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _check_message_trigger(
        self,
        submission_group_id: str,
        course_id: str,
        submission_group: dict,
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

    async def _process_ungraded_submission(self, submission_group: dict) -> None:
        """
        Process an ungraded submission detected via tutor endpoint.

        This uses the tutor endpoints which provide pre-filtered data:
        - GET /tutors/submission-groups?has_ungraded_submissions=true
        - GET /tutors/submission-groups/{id} for details
        """
        async with self._semaphore:
            sg_id = submission_group.get("id")
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

                # Extract key info
                course_content_id = sg_details.get("course_content_id")
                course_id = sg_details.get("course_id")
                latest_submission_id = sg_details.get("latest_submission_id")
                members = sg_details.get("members", [])

                # Skip if no submission or already processed
                if not latest_submission_id:
                    return

                if latest_submission_id in self._processed_artifacts:
                    return

                # Build trigger result
                result = TriggerCheckResult(
                    should_respond=True,
                    reason=f"Ungraded submission detected (has_ungraded_submissions=true)",
                    submission_trigger=SubmissionTrigger(
                        artifact_id=latest_submission_id,
                        submission_group_id=sg_id,
                        uploaded_by_course_member_id=members[0].get("course_member_id") if members else None,
                        version_identifier=None,
                        file_size=0,
                        uploaded_at=sg_details.get("latest_submission_at"),
                    ),
                )

                logger.info(
                    f"Ungraded submission for {sg_id}: "
                    f"artifact={latest_submission_id}, "
                    f"course_content={course_content_id}"
                )

                # Call the callback with enriched submission group data
                enriched_sg = {
                    **submission_group,
                    **sg_details,
                    "course_content_id": course_content_id,
                    "course_id": course_id,
                }

                await self.on_submission_trigger(result, enriched_sg)

                self._processed_artifacts.add(latest_submission_id)
                state.last_artifact_id = latest_submission_id
                state.last_processed = datetime.now()

            except Exception as e:
                logger.warning(f"Error processing ungraded submission {sg_id}: {e}")

            finally:
                state.processing = False

    async def _get_ungraded_submission_groups(self) -> list:
        """
        Get submission groups with ungraded submissions via tutor endpoint.

        Uses: GET /tutors/submission-groups?has_ungraded_submissions=true
        """
        try:
            kwargs = {"has_ungraded_submissions": True}

            if self.config.course_content_ids:
                # Filter by first course content ID (API might only support one)
                # For multiple, we'd need to make multiple calls
                all_groups = []
                for cc_id in self.config.course_content_ids:
                    groups = await self.client.tutors.get_submission_groups(
                        has_ungraded_submissions=True,
                        course_content_id=cc_id,
                    )
                    all_groups.extend(groups)
                return [
                    g.model_dump() if hasattr(g, "model_dump") else g
                    for g in all_groups
                ]

            elif self.config.course_ids:
                all_groups = []
                for course_id in self.config.course_ids:
                    groups = await self.client.tutors.get_submission_groups(
                        has_ungraded_submissions=True,
                        course_id=course_id,
                    )
                    all_groups.extend(groups)
                return [
                    g.model_dump() if hasattr(g, "model_dump") else g
                    for g in all_groups
                ]

            else:
                groups = await self.client.tutors.get_submission_groups(
                    has_ungraded_submissions=True,
                )
                return [
                    g.model_dump() if hasattr(g, "model_dump") else g
                    for g in groups
                ]

        except Exception as e:
            logger.error(f"Failed to get ungraded submission groups: {e}")
            return []

    async def _get_tutor_submission_group_details(self, submission_group_id: str) -> dict:
        """
        Get detailed submission group info via tutor endpoint.

        Uses: GET /tutors/submission-groups/{id}
        """
        try:
            sg = await self.client.tutors.submission_groups(submission_group_id)
            return sg.model_dump() if hasattr(sg, "model_dump") else dict(sg)
        except Exception as e:
            logger.warning(f"Failed to get tutor submission group details {submission_group_id}: {e}")
            return {}

    async def _get_submission_groups(self) -> list:
        """Get submission groups to check."""
        try:
            if self.config.course_content_ids:
                # Filter by course content IDs
                all_groups = []
                for cc_id in self.config.course_content_ids:
                    groups = await self.client.submission_groups.list(
                        course_content_id=cc_id,
                    )
                    all_groups.extend(groups)
                return all_groups

            elif self.config.course_ids:
                # Filter by course IDs
                all_groups = []
                for course_id in self.config.course_ids:
                    groups = await self.client.submission_groups.list(
                        course_id=course_id,
                    )
                    all_groups.extend(groups)
                return all_groups

            else:
                # Get all submission groups (should typically filter by course)
                logger.warning(
                    "No course_ids or course_content_ids configured - "
                    "this may return many submission groups"
                )
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
