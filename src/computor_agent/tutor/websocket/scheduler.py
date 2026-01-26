"""
WebSocket-based scheduler for the Tutor AI Agent.

Event-driven alternative to HTTP polling. Connects to the backend WebSocket,
subscribes to course channels, and processes messages in real-time.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Optional, Protocol

from computor_types.websocket import WSMessageNew

from computor_agent.tutor.config import TriggerConfig
from computor_agent.tutor.websocket.client import ComputorWebSocket, WebSocketError
from computor_agent.tutor.websocket.typing_manager import TypingManager

logger = logging.getLogger(__name__)


@dataclass
class ProcessingState:
    """Tracks processing state for a submission group."""

    submission_group_id: str
    last_processed: Optional[datetime] = None
    processing: bool = False
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
        """
        self.client = client
        self._ws = ws
        self.trigger_config = trigger_config or TriggerConfig()
        self.on_message_trigger = on_message_trigger
        self._cooldown_seconds = cooldown_seconds
        self._reconnect_delay = reconnect_delay_seconds
        self._max_reconnect_attempts = max_reconnect_attempts

        self._typing_manager = TypingManager(ws)
        self._semaphore = asyncio.Semaphore(max_concurrent_processing)

        # State tracking
        self._states: dict[str, ProcessingState] = {}
        self._course_ids: list[str] = []
        self._subscribed_channels: set[str] = set()  # Track subscribed channels
        self._running = False
        self._reconnect_count = 0
        self._event_task: Optional[asyncio.Task] = None

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

            # 2. Connect WebSocket
            await self._ws.connect()

            # 3. Subscribe to course channels
            if self._course_ids:
                channels = [f"course:{cid}" for cid in self._course_ids]
                await self._ws.subscribe(channels)
                self._subscribed_channels.update(channels)
                logger.info(f"Subscribed to {len(channels)} course channel(s)")

            # 4. Process unread messages (catch-up for messages received while offline)
            # This runs after WebSocket is connected so typing indicators work
            await self._process_unread_messages()

            # 5. Start event loop
            self._event_task = asyncio.create_task(self._event_loop())
            logger.info("WebSocket scheduler started")

            # Wait for the event loop to complete (or be cancelled)
            await self._event_task

        except asyncio.CancelledError:
            logger.info("WebSocket scheduler cancelled")
        except WebSocketError as e:
            # Initial connection failed - attempt reconnection
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
        """Discover courses the tutor is a member of."""
        try:
            # Use the tutors API to get courses
            # This should return courses where the authenticated user is a tutor
            courses = await self.client.tutors.get_courses()
            self._course_ids = [c.id for c in courses if c.id]
            logger.info(f"Discovered {len(self._course_ids)} course(s)")
        except Exception as e:
            logger.warning(f"Failed to discover courses: {e}")
            self._course_ids = []

    async def _process_unread_messages(self) -> None:
        """
        Process any unread messages with trigger tags.

        This is called at startup to catch up on messages that were
        sent while the agent was offline.
        """
        from computor_agent.tutor.trigger import TriggerChecker

        logger.info("Checking for unread messages (catch-up)...")

        try:
            # Get all course members with unread messages
            members = await self.client.tutors.get_course_members()

            members_with_unread = [m for m in members if (m.unread_message_count or 0) > 0]
            if not members_with_unread:
                logger.info("No unread messages found")
                return

            logger.info(f"Found {len(members_with_unread)} member(s) with unread messages")

            # Create trigger checker
            trigger_checker = TriggerChecker(
                messages_client=self.client.messages,
                course_members_client=self.client.course_members,
                config=self.trigger_config,
            )

            processed_count = 0

            for member in members_with_unread:
                try:
                    # Get course contents for this member
                    course_contents = await self.client.tutors.get_urse_member_id_course_contents(
                        member.id
                    )

                    for cc in course_contents:
                        if cc.unread_message_count <= 0:
                            continue

                        sg = cc.submission_group
                        if not sg or not sg.id:
                            continue

                        submission_group_id = sg.id

                        # Check for trigger
                        result = await trigger_checker.check_message_trigger(
                            submission_group_id, member.course_id
                        )

                        if result.should_respond and result.message_trigger:
                            logger.info(
                                f"Found unread trigger message: {result.message_trigger.message_id}"
                            )

                            # Build message data for processing
                            message_data = {
                                "id": result.message_trigger.message_id,
                                "content": result.message_trigger.content,
                                "title": result.message_trigger.title,
                                "author_id": result.message_trigger.author_id,
                                "submission_group_id": submission_group_id,
                            }

                            typing_channel = f"submission_group:{submission_group_id}"

                            # Subscribe to the submission_group channel for typing
                            if typing_channel not in self._subscribed_channels:
                                await self._ws.subscribe([typing_channel])
                                self._subscribed_channels.add(typing_channel)

                            # Process with typing indicator
                            async with self._typing_manager.typing(typing_channel):
                                await self._process_message(submission_group_id, message_data, typing_channel)

                            # Track as processed
                            state = self._get_or_create_state(submission_group_id)
                            state.last_message_id = result.message_trigger.message_id
                            processed_count += 1

                except Exception as e:
                    logger.warning(f"Error processing unread messages for member {member.id}: {e}")
                    continue

            logger.info(f"Catch-up complete: processed {processed_count} unread message(s)")

        except Exception as e:
            logger.warning(f"Error during unread message catch-up: {e}")

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

            except WebSocketError as e:
                logger.warning(f"WebSocket connection lost: {e}")

                if not self._running:
                    break

                # Attempt to reconnect
                reconnected = await self._reconnect()
                if not reconnected:
                    logger.error("Failed to reconnect after maximum attempts")
                    break

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

                # Reconnect
                await self._ws.connect()

                # Re-subscribe to all channels
                if self._subscribed_channels:
                    channels = list(self._subscribed_channels)
                    await self._ws.subscribe(channels)
                    logger.info(f"Re-subscribed to {len(channels)} channel(s)")

                # Reset reconnect count on successful connection
                self._reconnect_count = 0
                logger.info("WebSocket reconnected successfully")
                return True

            except Exception as e:
                logger.warning(f"Reconnection attempt failed: {e}")
                # Continue loop to retry

        return False

    async def _handle_event(self, event: dict) -> None:
        """Route event to appropriate handler."""
        event_type = event.get("type", "")

        # Log all non-ping events for debugging
        if event_type not in ("system:ping", "system:pong"):
            logger.info(f"WebSocket event received: type={event_type}")

        if event_type == "message:new":
            await self._handle_message_new(event)
        elif event_type == "channel:subscribed":
            channels = event.get("channels", [])
            logger.debug(f"Confirmed subscription to: {channels}")
        elif event_type == "channel:error":
            logger.warning(f"Channel error: {event}")
        else:
            logger.debug(f"Unhandled event type: {event_type}")

    async def _handle_message_new(self, event: dict) -> None:
        """
        Handle message:new event.

        Args:
            event: WebSocket event with type, channel, and data
        """
        event_channel = event.get("channel", "")
        event_data = event.get("data", {})

        # The event structure can be nested: event.data may contain {channel, data}
        # where the inner data is the actual message
        if "channel" in event_data and "data" in event_data:
            # Nested structure: event.data.channel and event.data.data
            channel = event_data.get("channel", "")
            data = event_data.get("data", {})
        else:
            # Flat structure: event.channel and event.data is the message
            channel = event_channel
            data = event_data

        # Log for debugging
        logger.debug(f"Received message:new event - channel={channel}")
        logger.debug(f"Message data keys: {list(data.keys())}")

        # Get submission_group_id from message data or channel
        submission_group_id = data.get("submission_group_id")

        # If channel is submission_group:*, extract from there as fallback
        if not submission_group_id and channel.startswith("submission_group:"):
            submission_group_id = channel.split(":", 1)[1]

        if not submission_group_id:
            logger.debug(f"Could not determine submission_group_id from event, skipping")
            return

        # Build channel for typing indicator (use submission_group format)
        typing_channel = f"submission_group:{submission_group_id}"

        # Subscribe to the submission_group channel if not already subscribed
        # This is required before sending typing events
        if typing_channel not in self._subscribed_channels:
            await self._ws.subscribe([typing_channel])
            self._subscribed_channels.add(typing_channel)
            logger.debug(f"Subscribed to {typing_channel} for typing events")

        # Check cooldown
        if self._should_skip(submission_group_id):
            logger.debug(f"Skipping {submission_group_id} due to cooldown")
            return

        # Check if this message has trigger tags
        title = data.get("title", "") or ""
        logger.debug(f"Checking trigger tags in title: '{title}'")
        logger.debug(f"Configured request tags: {[str(t) for t in self.trigger_config.request_tags]}")

        if not self._has_trigger_tags(data):
            logger.debug(f"Message does not have trigger tags")
            return

        # Check if this is an AI response (to avoid responding to ourselves)
        if self._is_ai_response(data):
            logger.debug(f"Ignoring AI response message")
            return

        # Check if message is already read
        if data.get("read", False):
            logger.debug(f"Ignoring already-read message")
            return

        message_id = data.get("id", "")
        state = self._get_or_create_state(submission_group_id)

        # Check if we already processed this message
        if state.last_message_id == message_id:
            logger.debug(f"Already processed message {message_id}")
            return

        # Check if already processing
        if state.processing:
            logger.debug(f"Already processing {submission_group_id}")
            return

        logger.info(f"Message trigger detected for {submission_group_id}: {data.get('title', '')[:50]}")

        # Process with semaphore and typing indicator
        async with self._semaphore:
            state.processing = True
            try:
                # Use typing_channel (submission_group:...) for typing indicator
                async with self._typing_manager.typing(typing_channel):
                    await self._process_message(submission_group_id, data, typing_channel)

                state.last_message_id = message_id
                state.last_processed = datetime.now()
            finally:
                state.processing = False

    async def _process_message(
        self,
        submission_group_id: str,
        message_data: dict,
        channel: str,
    ) -> None:
        """
        Process a triggered message.

        Args:
            submission_group_id: The submission group ID
            message_data: Message data from WebSocket event
            channel: The channel the message was received on
        """
        if not self.on_message_trigger:
            logger.warning("No message trigger callback configured")
            return

        # Build a trigger-like result for the callback
        # This matches the interface expected by the existing on_message_trigger callback
        from computor_agent.tutor.trigger import MessageTrigger, TriggerCheckResult

        trigger = MessageTrigger(
            message_id=message_data.get("id", ""),
            submission_group_id=submission_group_id,
            author_id=message_data.get("author_id", ""),
            author_course_member_id=message_data.get("author_course_member_id", ""),
            author_role="",  # Will be determined during processing
            content=message_data.get("content", ""),
            title=message_data.get("title", ""),
            created_at=None,
            root_message_id=message_data.get("id"),
            parent_id=message_data.get("parent_id"),
            is_follow_up=False,
        )

        result = TriggerCheckResult(
            should_respond=True,
            reason="WebSocket message:new event with trigger tags",
            message_trigger=trigger,
            root_message_id=message_data.get("id"),
        )

        # Call the callback with result, course_content (None for WS), and channel
        # The callback should handle fetching course_content if needed
        await self.on_message_trigger(result, None, channel)

    def _has_trigger_tags(self, message_data: dict) -> bool:
        """Check if message has any of the configured trigger tags."""
        if not self.trigger_config.is_enabled:
            return False

        title = message_data.get("title", "") or ""

        # Check if any request tag is in the title
        for tag in self.trigger_config.request_tags:
            tag_str = str(tag)  # e.g., "#ai::request"
            if tag_str in title:
                return True

        return False

    def _is_ai_response(self, message_data: dict) -> bool:
        """Check if message is an AI response (has response tag)."""
        title = message_data.get("title", "") or ""
        response_tag = str(self.trigger_config.response_tag)  # e.g., "#ai::response"
        return response_tag in title

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
