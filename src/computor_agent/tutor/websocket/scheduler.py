"""
WebSocket-based scheduler for the Tutor AI Agent.

Event-driven alternative to HTTP polling. Connects to the backend WebSocket
and relies on the auto-subscribed user inbox channel (`user:<own_id>`) to
receive every message the agent has read access to, across every scope.
"""

import asyncio
import logging
import re
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Awaitable, Callable, Optional, Protocol

from computor_types.messages import MessageThread

from computor_agent.api.metrics import MetricsCollector
from computor_agent.tutor.config import TriggerConfig
from computor_agent.tutor.websocket.client import ComputorWebSocket, WebSocketError
from computor_agent.tutor.websocket.typing_manager import TypingManager

logger = logging.getLogger(__name__)


MAX_AUTH_FAILURES = 3
STATE_MAX_AGE = timedelta(hours=24)


@dataclass
class ProcessingState:
    """Tracks processing state for a submission group."""

    submission_group_id: str
    last_processed: Optional[datetime] = None
    last_message_id: Optional[str] = None


class ComputorClientProtocol(Protocol):
    """Protocol for Computor API client with required endpoints."""

    @property
    def messages(self): ...

    @property
    def course_members(self): ...

    @property
    def tutors(self): ...


class WebSocketScheduler:
    """
    Event-driven scheduler using WebSocket connection.

    Subscribes to course channels and processes message:new events in real-time.
    Uses typing indicators to show activity while processing.

    Usage:
        ws = ComputorWebSocket(base_url, token)
        scheduler = WebSocketScheduler(
            client=computor_client,
            ws=ws,
            trigger_config=trigger_config,
            on_message_trigger=handle_message,
        )

        await scheduler.start()  # Blocks until stopped
        await scheduler.stop()
    """

    def __init__(
        self,
        client: ComputorClientProtocol,
        ws: ComputorWebSocket,
        trigger_config: Optional[TriggerConfig] = None,
        on_message_trigger: Optional[Callable] = None,
        cooldown_seconds: int = 60,
        max_concurrent_processing: int = 5,
        reconnect_delay_seconds: float = 30.0,
        max_reconnect_attempts: int = 0,  # 0 = unlimited
        token_provider: Optional[Callable[[], Awaitable[Optional[str]]]] = None,
        metrics: Optional[MetricsCollector] = None,
    ) -> None:
        """
        Initialize the WebSocket scheduler.

        Args:
            client: Computor API client (for REST calls)
            ws: WebSocket client instance
            trigger_config: Tag-based trigger configuration
            on_message_trigger: Async callback when message trigger detected
                Signature: async def callback(trigger_result, course_content, channel) -> None
            cooldown_seconds: Minimum seconds between processing same submission group
            max_concurrent_processing: Maximum concurrent message processing
            reconnect_delay_seconds: Delay between reconnection attempts
            max_reconnect_attempts: Maximum reconnection attempts (0 = unlimited)
            token_provider: Async callable that returns a fresh token for WebSocket auth.
                Called before each reconnection attempt. If None, the original token is reused.
        """
        self.client = client
        self._ws = ws
        self._token_provider = token_provider
        self.trigger_config = trigger_config or TriggerConfig()
        self.on_message_trigger = on_message_trigger
        self._metrics = metrics or MetricsCollector()
        self._cooldown_seconds = cooldown_seconds
        self._reconnect_delay = reconnect_delay_seconds
        self._max_reconnect_attempts = max_reconnect_attempts

        self._typing_manager = TypingManager(ws)
        self._semaphore = asyncio.Semaphore(max_concurrent_processing)

        # State tracking
        self._states: dict[str, ProcessingState] = {}
        self._locks: dict[str, asyncio.Lock] = {}  # Per-submission-group locks
        self._course_locks: dict[str, asyncio.Lock] = {}  # Per-course locks
        self._course_ids: list[str] = []
        self._subscribed_channels: set[str] = set()  # Track subscribed channels
        self._running = False
        self._reconnect_count = 0
        self._consecutive_auth_failures = 0
        self._event_task: Optional[asyncio.Task] = None
        self._periodic_catchup_task: Optional[asyncio.Task] = None
        self._periodic_catchup_interval = 60  # seconds

        # Reply-classification cache: avoid re-fetching /messages/{id}/thread for
        # the same untagged unread reply on every poll. Keyed by message_id; we
        # populate every message in a fetched thread so siblings hit the cache
        # too. Bounded LRU to keep memory finite on long-lived agents.
        self._reply_decisions: OrderedDict[str, dict] = OrderedDict()
        self._reply_cache_max = 10000

    @property
    def typing_manager(self) -> TypingManager:
        """Get the typing manager for external use."""
        return self._typing_manager

    async def start(self) -> None:
        """
        Start the WebSocket scheduler.

        1. Discovers courses from API
        2. Connects to WebSocket
        3. Subscribes to course channels
        4. Processes any unread messages (catch-up for offline period)
        5. Starts event processing loop
        """
        if self._running:
            logger.warning("WebSocket scheduler already running")
            return

        logger.info("Starting WebSocket scheduler")
        self._running = True

        try:
            # 1. Discover courses
            await self._discover_courses()

            if not self._course_ids:
                logger.warning("No courses found - scheduler will not receive events")

            # 2. Connect WebSocket. The server auto-subscribes us to
            # `user:<own_id>` and `global` on handshake; that user inbox
            # carries every message we have read access to, across every
            # scope, so no per-course subscription is needed.
            await self._ws.connect()
            logger.info(
                f"Listening on auto-subscribed user inbox "
                f"(user:{self._ws.user_id})"
            )

            # 3. Process unread messages (catch-up for messages received while offline)
            # This runs after WebSocket is connected so typing indicators work
            await self._process_unread_messages()

            # 4. Start event loop and periodic catch-up
            self._event_task = asyncio.create_task(self._event_loop())
            self._periodic_catchup_task = asyncio.create_task(self._periodic_catchup_loop())
            logger.info("WebSocket scheduler started")

            # Wait for both tasks (event loop is the primary one)
            await self._event_task

        except asyncio.CancelledError:
            logger.info("WebSocket scheduler cancelled")
        except (WebSocketError, asyncio.TimeoutError) as e:
            # Initial connection failed (including timeout) - attempt reconnection
            logger.warning(f"Initial WebSocket connection failed: {e}")
            if self._running:
                reconnected = await self._reconnect()
                if reconnected:
                    # Start the event loop after successful reconnection
                    self._event_task = asyncio.create_task(self._event_loop())
                    logger.info("WebSocket scheduler started after reconnection")
                    try:
                        await self._event_task
                    except asyncio.CancelledError:
                        logger.info("WebSocket scheduler cancelled")
                else:
                    logger.error("Failed to establish WebSocket connection")
        except Exception as e:
            logger.error(f"Unexpected error in WebSocket scheduler: {e}")
        finally:
            self._running = False

    async def stop(self) -> None:
        """Stop the WebSocket scheduler."""
        if not self._running:
            return

        logger.info("Stopping WebSocket scheduler")
        self._running = False

        # Stop all typing indicators
        await self._typing_manager.stop_all()

        # Cancel periodic catch-up
        if self._periodic_catchup_task:
            self._periodic_catchup_task.cancel()
            try:
                await self._periodic_catchup_task
            except asyncio.CancelledError:
                pass
            self._periodic_catchup_task = None

        # Cancel event loop
        if self._event_task:
            self._event_task.cancel()
            try:
                await self._event_task
            except asyncio.CancelledError:
                pass
            self._event_task = None

        # Disconnect WebSocket
        await self._ws.disconnect()
        logger.info("WebSocket scheduler stopped")

    async def _discover_courses(self) -> None:
        """Discover courses the tutor is a member of.

        Raises:
            Exception: If unauthorized (401) to stop the scheduler
        """
        try:
            # Use the tutors API to get courses
            # This should return courses where the authenticated user is a tutor
            courses = await self.client.tutors.get_courses()
            self._course_ids = [c.id for c in courses if c.id]
            logger.info(f"Discovered {len(self._course_ids)} course(s)")
        except Exception as e:
            error_str = str(e)
            # Check if it's an authorization error - stop immediately
            if "401" in error_str or "Unauthorized" in error_str:
                logger.error(f"Authentication failed: {e}")
                logger.error("The worker cannot continue without valid credentials. Please check your login.")
                # Re-raise to stop the scheduler
                raise
            else:
                logger.warning(f"Failed to discover courses: {e}")
                self._course_ids = []

    async def _check_all_courses(self) -> None:
        """Check all courses for unread messages (triggered by WebSocket event)."""
        # This runs as a fire-and-forget task from _handle_message_new, so any
        # exception here would be lost without this explicit log.
        try:
            for course_id in self._course_ids:
                await self._process_course_unread(course_id)
        except Exception as e:
            logger.exception(f"Error in WebSocket-triggered unread check: {e}")

    async def _process_unread_messages(self) -> None:
        """
        Process unread messages across all courses.

        Called at startup, after reconnection, and periodically as a safety net.
        Delegates to _process_course_unread for each course.
        """
        logger.info("Checking for unread messages (catch-up)...")

        self._evict_stale_states()

        if not self._course_ids:
            logger.debug("No courses to check for unread messages")
            return

        total = 0
        for course_id in self._course_ids:
            total += await self._process_course_unread(course_id)

        logger.info(f"Catch-up complete: processed {total} unread message(s)")
        self._metrics.catchup_complete()

    async def _process_course_unread(self, course_id: str) -> int:
        """
        Fetch and process unread messages for a single course.

        Two phases, with the per-course lock held only across the first:

          1. Scan + classify under the lock so concurrent WebSocket events
             don't kick off duplicate API list calls for the same course.
          2. Process each trigger entry with the lock released, so a new
             event arriving during a long LLM call can immediately run a
             fresh scan for this course instead of waiting for the current
             message to finish.

        Per-submission-group locks still prevent the same message from being
        processed twice; cooldown and last_message_id checks handle the case
        where two concurrent scans surface the same entry.
        """
        course_lock = self._get_or_create_course_lock(course_id)
        if course_lock.locked():
            logger.debug(f"Already classifying course {course_id}, skipping")
            return 0

        async with course_lock:
            trigger_entries = await self._classify_unread_for_course(course_id)

        if not trigger_entries:
            return 0

        return await self._process_trigger_entries(course_id, trigger_entries)

    async def _classify_unread_for_course(self, course_id: str) -> list[tuple]:
        """
        Phase 1: list unread messages and classify them into trigger entries.

        Returns a list of (msg, submission_group_id, root_message_id_or_None)
        tuples. On error returns [] so the scheduler keeps running.
        """
        agent_id = self.trigger_config.agent_user_id

        # Raise the per-page limit far above the backend default of 100 so a
        # reply sitting past position 100 in a course with a large backlog of
        # unread #ai requests doesn't get clipped out of view.
        MESSAGES_LIMIT = 1000

        trigger_entries: list[tuple] = []

        try:
            # 1. Fetch tagged unread messages (direct triggers).
            tagged_messages = await self.client.messages.list(
                course_id=course_id,
                mentions_me=True,
                unread=True,
                limit=MESSAGES_LIMIT,
            )

            # Each entry: (msg, submission_group_id, root_message_id_or_None).
            # For direct triggers root_id stays None — _process_message uses the
            # message_id itself as root in that case.
            # Messages without a resolvable submission_group_id are dropped
            # silently here so they don't show up in "Found N" and spam
            # skip-logs each poll.
            dropped_no_sg = 0
            for m in (tagged_messages or []):
                if agent_id and str(getattr(m, "author_id", "")) == str(agent_id):
                    continue
                if getattr(m, "is_deleted", False):
                    continue
                sg = getattr(m, "submission_group_id", None)
                if not sg:
                    dropped_no_sg += 1
                    continue
                trigger_entries.append((m, sg, None))

            # Ids of the direct @mention triggers, to skip them in the
            # follow-up (all_unread) pass below.
            mention_trigger_ids = {getattr(e[0], "id", None) for e in trigger_entries}

            # 2. Fetch untagged follow-up replies in AI threads.
            all_unread = await self.client.messages.list(
                course_id=course_id,
                unread=True,
                limit=MESSAGES_LIMIT,
            )

            # Aggregate rejection reasons instead of listing every message —
            # a course with a big backlog of #ai requests would otherwise
            # spam the log with hundreds of no-parent entries each poll.
            reject_counts: dict[str, int] = {}
            thread_errors: list[str] = []
            accepted_ids: list[str] = []
            to_ack: list[str] = []  # non-actionable msg_ids — flushed below

            cache_hits = 0
            for msg in (all_unread or []):
                msg_id = getattr(msg, "id", "?")
                title = getattr(msg, "title", "") or ""
                parent_id = getattr(msg, "parent_id", None)

                if getattr(msg, "is_deleted", False):
                    reject_counts["deleted"] = reject_counts.get("deleted", 0) + 1
                    to_ack.append(msg_id)
                    continue

                # A message that @mentions the agent is a direct trigger handled
                # in the tagged loop above; skip it here.
                if msg_id in mention_trigger_ids:
                    reject_counts["mention-trigger"] = reject_counts.get("mention-trigger", 0) + 1
                    continue
                # The agent's own past replies. Drain from unread so they don't
                # push new triggers past the per-page cap.
                if agent_id and str(getattr(msg, "author_id", "")) == str(agent_id):
                    reject_counts["own-message"] = reject_counts.get("own-message", 0) + 1
                    to_ack.append(msg_id)
                    continue
                if not parent_id:
                    # Parentless untagged messages are never follow-ups;
                    # remember so we don't re-evaluate them on every poll,
                    # and ack so they leave the unread list.
                    self._set_reply_decision(msg_id, has_ai=False)
                    reject_counts["no-parent"] = reject_counts.get("no-parent", 0) + 1
                    to_ack.append(msg_id)
                    continue

                # Fast-path: skip the thread API call if we already classified
                # this reply (or any sibling already pulled its thread).
                cached = self._get_reply_decision(msg_id)
                if cached is not None:
                    cache_hits += 1
                    if not cached["has_ai"]:
                        reject_counts["cached:no-ai"] = reject_counts.get("cached:no-ai", 0) + 1
                        continue
                    sg = getattr(msg, "submission_group_id", None) or cached.get("sg")
                    root_id = cached.get("root_id")
                    if sg and root_id:
                        accepted_ids.append(msg_id)
                        trigger_entries.append((msg, sg, root_id))
                        continue
                    # Cache lacks sg or root — drop and refetch below.
                    self._reply_decisions.pop(msg_id, None)

                try:
                    thread_raw = await self.client.messages.thread(msg.id)
                    thread = MessageThread.model_validate(thread_raw)
                except Exception as e:
                    thread_errors.append(f"{msg_id}:{type(e).__name__}")
                    continue

                has_ai = bool(agent_id) and any(
                    str(getattr(m, "author_id", "")) == str(agent_id)
                    for m in thread.messages
                )
                root_id = getattr(thread, "root_message_id", None)

                # Populate cache for every message in this thread so siblings
                # encountered later in this loop or on the next poll skip
                # the API.
                for m in thread.messages:
                    m_id = getattr(m, "id", None)
                    if m_id:
                        self._set_reply_decision(
                            m_id,
                            has_ai=has_ai,
                            root_id=root_id,
                            sg=getattr(m, "submission_group_id", None),
                        )

                if not has_ai:
                    reject_counts["no-ai-in-thread"] = reject_counts.get("no-ai-in-thread", 0) + 1
                    # Replies in non-AI threads aren't ours to handle; ack so
                    # they don't accumulate in the unread list.
                    to_ack.append(msg_id)
                    continue

                sg = getattr(msg, "submission_group_id", None)
                if not sg:
                    for m in thread.messages:
                        msg_sg = getattr(m, "submission_group_id", None)
                        if msg_sg:
                            sg = msg_sg
                            break
                if not sg:
                    reject_counts["no-sg-in-thread"] = reject_counts.get("no-sg-in-thread", 0) + 1
                    continue

                accepted_ids.append(msg_id)
                trigger_entries.append((msg, sg, root_id))

            # Drain non-actionable messages from the agent's unread inbox.
            # Bounded concurrency so a 1000-message backlog doesn't slam the
            # backend. Errors are swallowed inside _ack_unread.
            acked = 0
            if to_ack:
                ack_sem = asyncio.Semaphore(8)

                async def _bounded_ack(mid: str) -> None:
                    async with ack_sem:
                        await self._ack_unread(mid)

                await asyncio.gather(
                    *(_bounded_ack(mid) for mid in to_ack),
                    return_exceptions=True,
                )
                acked = len(to_ack)

            log_parts = [
                f"tagged={len(tagged_messages or [])}",
                f"all_unread={len(all_unread or [])}",
                f"dropped_no_sg={dropped_no_sg}",
                f"cache_hits={cache_hits}",
                f"acked={acked}",
                f"triggers={len(trigger_entries)}",
            ]
            if reject_counts:
                log_parts.append(f"rejected={reject_counts}")
            if thread_errors:
                log_parts.append(f"thread_errors={thread_errors}")
            if accepted_ids:
                log_parts.append(f"accepted={accepted_ids}")
            logger.info(f"Unread scan course {course_id}: " + ", ".join(log_parts))

            if len(all_unread or []) >= MESSAGES_LIMIT:
                logger.warning(
                    f"Unread message list hit the per-page limit ({MESSAGES_LIMIT}) "
                    f"for course {course_id} — follow-ups past this page are invisible "
                    f"until the tutor's unread backlog is reduced."
                )

        except Exception as e:
            logger.warning(f"Error classifying unread messages for course {course_id}: {e}")
            return []

        return trigger_entries

    async def _process_trigger_entries(
        self, course_id: str, trigger_entries: list[tuple]
    ) -> int:
        """
        Phase 2: process each classified trigger entry.

        Runs without the per-course lock so a new WebSocket event arriving
        during a long LLM call can immediately kick off a fresh classification
        pass for the same course. The per-submission-group lock,
        last_message_id check, and cooldown together prevent two concurrent
        passes from processing the same message twice.
        """
        processed_count = 0

        try:
            for msg, submission_group_id, thread_root_id in trigger_entries:
                message_id = getattr(msg, "id", "")
                # Classification already happened in _classify_unread_for_course:
                # direct @mention triggers carry root_id=None, follow-ups carry
                # the thread root id.
                is_follow_up = thread_root_id is not None

                state = self._get_or_create_state(submission_group_id)

                if state.last_message_id == message_id:
                    logger.info(
                        f"Skipping message {message_id}: already recorded as last "
                        f"processed for submission_group {submission_group_id}"
                    )
                    self._metrics.message_skipped(course_id)
                    continue

                # Skip if already being processed or in cooldown
                lock = self._get_or_create_lock(submission_group_id)
                if lock.locked():
                    logger.info(
                        f"Skipping message {message_id}: submission_group "
                        f"{submission_group_id} already being processed"
                    )
                    self._metrics.message_skipped(course_id)
                    continue

                if self._should_skip(submission_group_id):
                    logger.info(
                        f"Skipping message {message_id}: submission_group "
                        f"{submission_group_id} in cooldown"
                    )
                    self._metrics.message_skipped(course_id)
                    continue

                trigger_type = "follow-up" if is_follow_up else "direct"
                logger.info(f"Processing unread {trigger_type} message: {message_id}")
                self._metrics.message_seen(course_id)

                message_data = {
                    "id": message_id,
                    "content": getattr(msg, "content", "") or "",
                    "title": title,
                    "author_id": getattr(msg, "author_id", "") or "",
                    "submission_group_id": submission_group_id,
                }

                typing_channel = f"submission_group:{submission_group_id}"

                # Subscribe to submission_group channel for typing indicators
                if typing_channel not in self._subscribed_channels:
                    await self._ws.subscribe([typing_channel])
                    self._subscribed_channels.add(typing_channel)

                async with lock:
                    # Re-check after acquiring lock
                    if state.last_message_id == message_id:
                        logger.info(
                            f"Skipping message {message_id}: processed by another "
                            f"task while waiting for lock"
                        )
                        self._metrics.message_skipped(course_id)
                        continue

                    async with self._semaphore:
                        try:
                            async with self._typing_manager.typing(typing_channel):
                                await self._process_message(
                                    submission_group_id, message_data, typing_channel,
                                    is_follow_up=is_follow_up,
                                    thread_root_id=thread_root_id,
                                )
                        except Exception as e:
                            logger.error(f"Failed to process message {message_id}: {e}")
                            self._metrics.message_failed(course_id)
                            continue

                    await self._ws.mark_read(typing_channel, message_id)
                    state.last_message_id = message_id
                    state.last_processed = datetime.now()

                    # Our reply just landed in the thread — flip cached
                    # siblings so they classify as triggers on the next poll
                    # instead of being held back by a stale "no AI" verdict.
                    self._mark_thread_has_ai(thread_root_id or message_id)

                processed_count += 1
                self._metrics.message_succeeded(course_id)

        except Exception as e:
            logger.warning(f"Error processing trigger entries for course {course_id}: {e}")

        return processed_count

    async def _event_loop(self) -> None:
        """Main event processing loop with automatic reconnection."""
        while self._running:
            try:
                async for event in self._ws.receive():
                    if not self._running:
                        break

                    try:
                        await self._handle_event(event)
                    except Exception as e:
                        logger.exception(f"Error handling event: {e}")

                # If we exit the loop normally (not running), break out
                if not self._running:
                    break

            except (WebSocketError, asyncio.TimeoutError) as e:
                logger.warning(f"WebSocket connection lost: {e}")

                if not self._running:
                    break

                # Attempt to reconnect
                reconnected = await self._reconnect()
                if not reconnected:
                    logger.error("Failed to reconnect after maximum attempts")
                    break

    async def _periodic_catchup_loop(self) -> None:
        """Periodically check for unread messages as a safety net.

        WebSocket events may be missed during brief disconnects or race
        conditions. This loop runs alongside the event loop, polling for
        unread messages every `_periodic_catchup_interval` seconds.
        """
        while self._running:
            try:
                await asyncio.sleep(self._periodic_catchup_interval)
                if not self._running:
                    break
                logger.debug("Periodic catch-up: checking for unread messages")
                await self._process_unread_messages()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Error in periodic catch-up: {e}")

    async def _reconnect(self) -> bool:
        """
        Attempt to reconnect to the WebSocket server.

        Keeps trying until successful, stopped, or max attempts reached.

        Returns:
            True if reconnection successful, False if max attempts reached or stopped
        """
        while self._running:
            self._reconnect_count += 1

            # Check max attempts (0 = unlimited)
            if self._max_reconnect_attempts > 0 and self._reconnect_count > self._max_reconnect_attempts:
                return False

            logger.info(
                f"Attempting to reconnect in {self._reconnect_delay}s "
                f"(attempt {self._reconnect_count}"
                f"{f'/{self._max_reconnect_attempts}' if self._max_reconnect_attempts > 0 else ''})..."
            )

            # Wait before reconnecting
            await asyncio.sleep(self._reconnect_delay)

            if not self._running:
                return False

            try:
                # Disconnect cleanly first (if still connected)
                try:
                    await self._ws.disconnect()
                except Exception:
                    pass

                # Refresh token before reconnecting
                token_ok = True
                if self._token_provider:
                    try:
                        new_token = await self._token_provider()
                        if new_token:
                            self._ws.update_token(new_token)
                            self._consecutive_auth_failures = 0
                            logger.info("Refreshed WebSocket authentication token")
                        else:
                            self._consecutive_auth_failures += 1
                            token_ok = False
                            logger.warning(
                                f"Token provider returned no token "
                                f"({self._consecutive_auth_failures}/{MAX_AUTH_FAILURES} failures)"
                            )
                    except Exception as e:
                        self._consecutive_auth_failures += 1
                        token_ok = False
                        logger.warning(
                            f"Failed to refresh token: {e} "
                            f"({self._consecutive_auth_failures}/{MAX_AUTH_FAILURES} failures)"
                        )

                    if self._consecutive_auth_failures >= MAX_AUTH_FAILURES:
                        logger.error(
                            "Authentication failed repeatedly. "
                            "Please check your credentials and restart the agent."
                        )
                        return False

                # Reconnect
                await self._ws.connect()

                # Re-subscribe to all channels
                if self._subscribed_channels:
                    channels = list(self._subscribed_channels)
                    await self._ws.subscribe(channels)
                    logger.info(f"Re-subscribed to {len(channels)} channel(s)")

                # Reset counters on successful connection
                self._reconnect_count = 0
                self._consecutive_auth_failures = 0
                logger.info("WebSocket reconnected successfully")

                # Process any unread messages that arrived while disconnected
                await self._process_unread_messages()

                return True

            except Exception as e:
                logger.warning(f"Reconnection attempt failed: {e}")
                # Continue loop to retry

        return False

    async def _handle_event(self, event: dict) -> None:
        """Route event to appropriate handler."""
        event_type = event.get("type", "")

        # Log routine events at DEBUG level, meaningful events at INFO.
        # `read:update` is broadcast back for every messages.reads we issue
        # (a flush of the ack queue can fire hundreds at once); keep it noise.
        if event_type in ("system:ping", "system:pong", "read:update"):
            logger.debug(f"WebSocket event: {event_type}")
        else:
            logger.info(f"WebSocket event received: type={event_type}")
            self._metrics.event_received()

        if event_type == "message:new":
            await self._handle_message_new(event)
        elif event_type == "channel:subscribed":
            channels = event.get("channels", [])
            self._ws.confirm_subscription(channels)
            logger.debug(f"Confirmed subscription to: {channels}")
        elif event_type == "channel:error":
            logger.warning(f"Channel error: {event}")
        else:
            logger.debug(f"Unhandled event type: {event_type}")

    async def _handle_message_new(self, event: dict) -> None:
        """
        Handle message:new as a wake-up signal to fetch unread messages.

        Instead of processing the message from the event payload directly,
        we use the event as a notification to fetch unread messages via REST.
        This gives us a single processing path shared with catch-up polling,
        eliminating race conditions between the two.

        Note: message:new events arrive on the user inbox channel
        (`user:<own_id>`) regardless of the message's scope, so we check
        all courses for unread messages rather than trying to map back to
        a specific course.
        """
        event_channel = event.get("channel", "")
        event_data = event.get("data", {})

        # Handle nested event structure
        if "channel" in event_data and "data" in event_data:
            channel = event_data.get("channel", "")
            data = event_data.get("data", {})
        else:
            channel = event_channel
            data = event_data

        logger.info(f"Received message:new event - channel={channel}")

        # Quick filter: ignore our own AI responses to avoid unnecessary REST calls
        if self._is_ai_response(data):
            logger.info(f"Ignoring AI response message (title='{data.get('title', '')}')")
            return

        # Use the event as a wake-up signal to check all courses for unread messages.
        # Per-course locks prevent redundant concurrent fetches.
        asyncio.create_task(self._check_all_courses())

    async def _process_message(
        self,
        submission_group_id: str,
        message_data: dict,
        channel: str,
        is_follow_up: bool = False,
        thread_root_id: Optional[str] = None,
    ) -> None:
        """
        Process a triggered message.

        Args:
            submission_group_id: The submission group ID
            message_data: Message data from WebSocket event
            channel: The channel the message was received on
            is_follow_up: Whether this is a follow-up in an AI conversation
            thread_root_id: Root message ID of the thread (if follow-up)
        """
        if not self.on_message_trigger:
            logger.warning("No message trigger callback configured")
            return

        # Build a trigger-like result for the callback
        # This matches the interface expected by the existing on_message_trigger callback
        from computor_agent.tutor.trigger import MessageTrigger, TriggerCheckResult

        message_id = message_data.get("id", "")
        root_id = thread_root_id if is_follow_up else message_id

        trigger = MessageTrigger(
            message_id=message_id,
            submission_group_id=submission_group_id,
            author_id=message_data.get("author_id", ""),
            author_course_member_id=message_data.get("author_course_member_id", ""),
            author_role="",  # Will be determined during processing
            content=message_data.get("content", ""),
            title=message_data.get("title", ""),
            created_at=None,
            root_message_id=root_id,
            parent_id=message_data.get("parent_id"),
            is_follow_up=is_follow_up,
        )

        reason = "Follow-up reply in agent conversation" if is_follow_up else "WebSocket message:new event mentioning the agent"
        result = TriggerCheckResult(
            should_respond=True,
            reason=reason,
            message_trigger=trigger,
            root_message_id=root_id,
        )

        # Call the callback with result, course_content (None for WS), and channel
        # The callback should handle fetching course_content if needed
        await self.on_message_trigger(result, None, channel)

    @staticmethod
    def _match_tag(tag_str: str, title: str) -> bool:
        """Match a tag as a standalone token (not as part of a longer tag like #ai::request-rejected).

        Prevents matching when followed by word chars, hyphens, or colons
        (which would indicate a continuation like -rejected or ::sub),
        but allows punctuation like commas, periods, etc.
        """
        return bool(re.search(r'(?<!\S)' + re.escape(tag_str) + r'(?![\w:-])', title))

    def _is_ai_response(self, message_data: dict) -> bool:
        """Whether this message was authored by the agent itself (its own past
        reply) — identified by author_id now, not a response tag."""
        agent_id = self.trigger_config.agent_user_id
        return bool(agent_id) and str(message_data.get("author_id", "")) == str(agent_id)

    def _should_skip(self, submission_group_id: str) -> bool:
        """Check if submission group should be skipped due to cooldown."""
        state = self._states.get(submission_group_id)
        if not state or not state.last_processed:
            return False

        cooldown = timedelta(seconds=self._cooldown_seconds)
        return datetime.now() - state.last_processed < cooldown

    def _get_or_create_state(self, submission_group_id: str) -> ProcessingState:
        """Get or create processing state for a submission group."""
        if submission_group_id not in self._states:
            self._states[submission_group_id] = ProcessingState(
                submission_group_id=submission_group_id
            )
        return self._states[submission_group_id]

    def _get_or_create_lock(self, submission_group_id: str) -> asyncio.Lock:
        """Get or create a per-group processing lock."""
        if submission_group_id not in self._locks:
            self._locks[submission_group_id] = asyncio.Lock()
        return self._locks[submission_group_id]

    def _get_or_create_course_lock(self, course_id: str) -> asyncio.Lock:
        """Get or create a per-course lock for fetch-unread operations."""
        if course_id not in self._course_locks:
            self._course_locks[course_id] = asyncio.Lock()
        return self._course_locks[course_id]

    def _get_reply_decision(self, message_id: str) -> Optional[dict]:
        """Look up a cached classification, refreshing LRU position on hit."""
        cached = self._reply_decisions.get(message_id)
        if cached is not None:
            self._reply_decisions.move_to_end(message_id)
        return cached

    def _set_reply_decision(
        self,
        message_id: str,
        *,
        has_ai: bool,
        root_id: Optional[str] = None,
        sg: Optional[str] = None,
    ) -> None:
        """Cache a classification, evicting the oldest entry once over the cap."""
        self._reply_decisions[message_id] = {
            "has_ai": has_ai,
            "root_id": root_id,
            "sg": sg,
        }
        self._reply_decisions.move_to_end(message_id)
        while len(self._reply_decisions) > self._reply_cache_max:
            self._reply_decisions.popitem(last=False)

    async def _ack_unread(self, message_id: str) -> None:
        """Best-effort: tell the backend we've seen a non-actionable message.

        Without this, the agent's unread inbox grows unboundedly (parentless
        posts, replies in non-AI threads, the agent's own AI responses) and
        eventually pushes new tagged triggers past the per-page cap on the
        unread list, making them invisible to the scheduler.
        """
        try:
            await self.client.messages.reads(id=message_id)
        except Exception as e:
            logger.debug(f"Failed to ack non-actionable message {message_id}: {e}")

    def _mark_thread_has_ai(self, root_id: str) -> None:
        """Flip every cached entry in this thread to has_ai=True.

        Called after the agent itself posts a response, so untagged siblings
        still in the unread list classify as triggers on the next poll instead
        of being held back by a stale 'no AI in this thread' verdict.
        """
        if not root_id:
            return
        for entry in self._reply_decisions.values():
            if entry.get("root_id") == root_id and not entry.get("has_ai"):
                entry["has_ai"] = True

    def _evict_stale_states(self) -> None:
        """Remove processing states older than STATE_MAX_AGE to prevent memory leaks.

        Only evicts states that have been processed (last_processed is set) and are
        older than STATE_MAX_AGE. States with last_processed=None are freshly created
        and should not be evicted.
        """
        now = datetime.now()
        stale_ids = [
            sid for sid, state in self._states.items()
            if state.last_processed is not None and (now - state.last_processed) > STATE_MAX_AGE
        ]
        for sid in stale_ids:
            del self._states[sid]
            self._locks.pop(sid, None)
        if stale_ids:
            logger.debug(f"Evicted {len(stale_ids)} stale processing state(s)")

    def get_stats(self) -> dict:
        """Get scheduler statistics."""
        return {
            "running": self._running,
            "connected": self._ws.is_connected,
            "courses": len(self._course_ids),
            "tracked_groups": len(self._states),
            "active_typing": self._typing_manager.active_channels,
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
