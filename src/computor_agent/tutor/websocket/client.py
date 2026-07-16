"""
WebSocket client for Computor backend.

Provides a wrapper around the websockets library with:
- Single-attempt connect (retry policy is owned by the caller)
- Heartbeat/ping-pong handling with dead-connection detection
- Type-safe message sending using computor_types.websocket DTOs
"""

import asyncio
import json
import logging
import time
from typing import AsyncIterator, Optional

import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException

from computor_types.websocket import (
    WSChannelSubscribe,
    WSChannelUnsubscribe,
    WSPing,
    WSPong,
    WSReadMark,
    WSTypingStart,
    WSTypingStop,
)

# Recommended ping interval from server config (WS_PING_INTERVAL)
PING_INTERVAL = 25  # seconds

# If no frame at all (pong, event, anything) arrives for this long even though
# we ping every PING_INTERVAL, the connection is considered dead and force-closed
# so the receive loop unblocks and the scheduler can reconnect.
ACTIVITY_TIMEOUT = 3 * PING_INTERVAL  # seconds

logger = logging.getLogger(__name__)


class WebSocketError(Exception):
    """Base exception for WebSocket errors."""

    pass


class WebSocketConnectionError(WebSocketError):
    """Raised when WebSocket connection fails."""

    pass


class ComputorWebSocket:
    """
    WebSocket client for Computor backend.

    Handles connection management, reconnection, and message sending/receiving.
    Implements the protocol as specified in the WebSocket Client Implementation Guide.

    Usage:
        ws = ComputorWebSocket(base_url="http://api.example.com", token="...")
        await ws.connect()
        await ws.subscribe(["course:abc-123"])

        async for event in ws.receive():
            print(event)

        await ws.disconnect()
    """

    def __init__(
        self,
        base_url: str,
        token: str,
        connect_timeout: float = 30.0,
    ):
        """
        Initialize the WebSocket client.

        Args:
            base_url: Backend API base URL (http:// or https://)
            token: Authentication token (Bearer token)
            connect_timeout: Timeout for connection handshake (seconds)
        """
        # Convert http(s) to ws(s)
        ws_base = base_url.replace("https://", "wss://").replace("http://", "ws://")
        self._ws_base = f"{ws_base}/ws"
        self._token = token

        self._connect_timeout = connect_timeout

        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._connected = False
        self._user_id: Optional[str] = None
        self._ping_task: Optional[asyncio.Task] = None
        self._last_activity = 0.0

        # Subscription tracking
        self._pending_subscriptions: set[str] = set()
        self._confirmed_subscriptions: set[str] = set()
        self._subscription_events: dict[str, asyncio.Event] = {}

    def update_token(self, token: str) -> None:
        """Update the authentication token (e.g., after a refresh)."""
        self._token = token

    @property
    def ws_url(self) -> str:
        """Build full WS URL with token (avoid storing token in plain attribute)."""
        return f"{self._ws_base}?token={self._token}"

    @property
    def _masked_ws_url(self) -> str:
        """Return WS URL with token masked for logging."""
        return f"{self._ws_base}?token=***"

    @property
    def is_connected(self) -> bool:
        """Check if WebSocket is currently connected."""
        return self._connected and self._ws is not None

    @property
    def user_id(self) -> Optional[str]:
        """Get the authenticated user ID (set after connection)."""
        return self._user_id

    async def connect(self) -> None:
        """
        Connect to the WebSocket server (single attempt).

        Waits for the system:connected event and starts the ping loop.
        Retry policy is owned by the caller — this method either establishes
        a live connection or raises; it never returns unconnected.

        Raises:
            WebSocketConnectionError: If the connection attempt fails.
        """
        logger.info(f"Connecting to WebSocket: {self._masked_ws_url}")
        try:
            self._ws = await websockets.connect(
                self.ws_url,
                ping_interval=20.0,  # Protocol-level keepalive (handled by the library)
                ping_timeout=20.0,   # Missing protocol pong closes the connection
                open_timeout=self._connect_timeout,
                close_timeout=10.0,
            )
        except asyncio.TimeoutError as e:
            raise WebSocketConnectionError(
                f"Connection timed out after {self._connect_timeout}s: {self._masked_ws_url}"
            ) from e
        except (WebSocketException, OSError) as e:
            error_details = self._extract_error_details(e)
            raise WebSocketConnectionError(
                f"Failed to connect: {error_details['message']} "
                f"(type={error_details['error_type']}, url={error_details['url']})"
            ) from e

        # Wait for system:connected event
        try:
            response = await asyncio.wait_for(self._ws.recv(), timeout=10.0)
            data = json.loads(response)
            if data.get("type") == "system:connected":
                self._user_id = data.get("user_id")
                logger.info(f"WebSocket connected as user {self._user_id}")
            else:
                logger.warning(f"Expected system:connected, got: {data.get('type')}")
        except asyncio.TimeoutError:
            logger.warning("Timeout waiting for system:connected event")
        except json.JSONDecodeError as e:
            logger.warning(f"Malformed greeting from server: {e}")
        except (ConnectionClosed, OSError) as e:
            # Server accepted the handshake but dropped us during the greeting
            await self._close_transport()
            raise WebSocketConnectionError(
                f"Connection lost while waiting for system:connected: {e}"
            ) from e

        self._connected = True
        self._last_activity = time.monotonic()

        # Start ping loop
        self._ping_task = asyncio.create_task(self._ping_loop())

    async def _close_transport(self) -> None:
        """Best-effort close of the underlying transport."""
        if self._ws:
            try:
                await self._ws.close()
            except Exception as e:
                logger.debug(f"Error closing WebSocket transport: {e}")
            self._ws = None

    async def disconnect(self) -> None:
        """Disconnect from the WebSocket server."""
        self._connected = False

        # Cancel ping task
        if self._ping_task:
            self._ping_task.cancel()
            try:
                await self._ping_task
            except asyncio.CancelledError:
                pass
            self._ping_task = None

        if self._ws:
            try:
                await self._ws.close()
                logger.info("WebSocket disconnected")
            except Exception as e:
                logger.warning(f"Error closing WebSocket: {e}")
            finally:
                self._ws = None
                self._user_id = None
                self._pending_subscriptions.clear()
                self._confirmed_subscriptions.clear()
                self._subscription_events.clear()

    async def subscribe(self, channels: list[str]) -> None:
        """
        Subscribe to one or more channels.

        Args:
            channels: List of channel names (e.g., ["course:abc-123"])
        """
        if not self.is_connected:
            raise WebSocketError("Not connected")

        # Track pending subscriptions with events for waiting
        for ch in channels:
            self._pending_subscriptions.add(ch)
            if ch not in self._subscription_events:
                self._subscription_events[ch] = asyncio.Event()

        msg = WSChannelSubscribe(type="channel:subscribe", channels=channels)
        await self._send(msg.model_dump())
        logger.info(f"Requested subscription to channels: {channels}")

    def confirm_subscription(self, channels: list[str]) -> None:
        """Mark channels as confirmed by the server (called on channel:subscribed event)."""
        for ch in channels:
            self._pending_subscriptions.discard(ch)
            self._confirmed_subscriptions.add(ch)
            if ch in self._subscription_events:
                self._subscription_events[ch].set()

    def is_subscribed(self, channel: str) -> bool:
        """Check if a channel subscription has been confirmed by the server."""
        return channel in self._confirmed_subscriptions

    async def wait_subscribed(self, channel: str, timeout: float = 2.0) -> bool:
        """Wait for a channel subscription to be confirmed. Returns False on timeout."""
        if channel in self._confirmed_subscriptions:
            return True
        event = self._subscription_events.get(channel)
        if not event:
            return False
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False

    async def unsubscribe(self, channels: list[str]) -> None:
        """
        Unsubscribe from one or more channels.

        Args:
            channels: List of channel names to unsubscribe from
        """
        if not self.is_connected:
            raise WebSocketError("Not connected")

        msg = WSChannelUnsubscribe(type="channel:unsubscribe", channels=channels)
        await self._send(msg.model_dump())
        logger.info(f"Unsubscribed from channels: {channels}")

    async def send_typing_start(self, channel: str) -> None:
        """
        Send typing start indicator.

        Args:
            channel: Channel to show typing in (e.g., "submission_group:123")
        """
        if not self.is_connected:
            return  # Silently ignore if not connected

        msg = WSTypingStart(type="typing:start", channel=channel)
        await self._send(msg.model_dump())
        logger.debug(f"Sent typing:start to {channel}")

    async def send_typing_stop(self, channel: str) -> None:
        """
        Send typing stop indicator.

        Args:
            channel: Channel to stop typing in
        """
        if not self.is_connected:
            return  # Silently ignore if not connected

        msg = WSTypingStop(type="typing:stop", channel=channel)
        await self._send(msg.model_dump())
        logger.debug(f"Sent typing:stop to {channel}")

    async def mark_read(self, channel: str, message_id: str) -> None:
        """
        Mark a message as read.

        Args:
            channel: Channel the message belongs to (e.g., "submission_group:123")
            message_id: ID of the message to mark as read
        """
        if not self.is_connected:
            return  # Silently ignore if not connected

        msg = WSReadMark(type="read:mark", channel=channel, message_id=message_id)
        await self._send(msg.model_dump())
        logger.debug(f"Marked message {message_id} as read in {channel}")

    async def send_ping(self) -> None:
        """Send ping to server for keep-alive."""
        if not self.is_connected:
            return

        msg = WSPing(type="system:ping")
        await self._send(msg.model_dump())
        logger.debug("Sent ping")

    async def send_pong(self) -> None:
        """Send pong response to server ping."""
        if not self.is_connected:
            return

        msg = WSPong(type="system:pong")
        await self._send(msg.model_dump())
        logger.debug("Sent pong")

    async def receive(self) -> AsyncIterator[dict]:
        """
        Receive events from the WebSocket.

        Yields parsed JSON events. Handles ping/pong and errors automatically.

        Yields:
            dict: Parsed event data with 'type' field

        Raises:
            WebSocketError: If connection is lost and reconnection fails
        """
        if not self._ws:
            raise WebSocketError("Not connected")

        try:
            async for message in self._ws:
                # Any inbound frame proves the link is alive
                self._last_activity = time.monotonic()
                try:
                    event = json.loads(message)
                    event_type = event.get("type", "")

                    # Handle system ping automatically
                    if event_type == "system:ping":
                        await self.send_pong()
                        continue

                    # Handle system pong (response to our ping)
                    if event_type == "system:pong":
                        logger.debug("Received pong")
                        continue

                    # Handle system errors
                    if event_type == "system:error":
                        error_code = event.get("code", "UNKNOWN")
                        error_msg = event.get("message", "Unknown error")
                        logger.error(f"WebSocket error [{error_code}]: {error_msg}")
                        # Yield the error event so callers can handle it if needed
                        yield event
                        continue

                    yield event

                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse WebSocket message: {e}")
                    continue

        except ConnectionClosed as e:
            logger.warning(f"WebSocket connection closed: {e}")
            self._connected = False
            raise WebSocketError(f"Connection closed: {e}") from e
        except (AttributeError, OSError) as e:
            # AttributeError: websockets transport invalidated (e.g. 'NoneType'
            # has no attribute 'resume_reading') — happens when the underlying
            # connection is lost while iterating.
            # OSError: low-level socket errors during receive.
            logger.warning(f"WebSocket connection lost: {e}")
            self._connected = False
            raise WebSocketError(f"Connection lost: {e}") from e

    async def _ping_loop(self) -> None:
        """
        Background task that sends periodic pings to keep connection alive.

        Sends system:ping every PING_INTERVAL seconds (25s by default) and
        watches for inbound activity: the server answers each ping with
        system:pong, so if no frame at all arrives for ACTIVITY_TIMEOUT the
        connection is half-open. Force-closing it unblocks the receive loop,
        which raises and routes the scheduler into its reconnect path.
        """
        try:
            while self._connected:
                await asyncio.sleep(PING_INTERVAL)
                if not self._connected:
                    break
                try:
                    await self.send_ping()
                except WebSocketError:
                    # Connection lost, exit loop
                    break
                if time.monotonic() - self._last_activity > ACTIVITY_TIMEOUT:
                    logger.warning(
                        f"No WebSocket activity for {ACTIVITY_TIMEOUT}s despite "
                        f"pings every {PING_INTERVAL}s — closing dead connection"
                    )
                    self._connected = False
                    if self._ws:
                        try:
                            await self._ws.close()
                        except Exception as e:
                            logger.debug(f"Error closing dead WebSocket: {e}")
                    break
        except asyncio.CancelledError:
            # Task cancelled - expected during disconnect
            pass
        except Exception as e:
            logger.warning(f"Error in ping loop: {e}")

    async def _send(self, data: dict) -> None:
        """Send JSON data to the WebSocket."""
        if not self._ws:
            raise WebSocketError("Not connected")

        try:
            await self._ws.send(json.dumps(data))
        except (ConnectionClosed, OSError) as e:
            self._connected = False
            raise WebSocketError(f"Connection closed while sending: {e}") from e

    def _extract_error_details(self, e: Exception) -> dict:
        """
        Extract detailed error information from various exception types.

        Args:
            e: The exception to extract details from

        Returns:
            dict: Containing error_type, message, errno, host, port, url
        """
        details = {
            "error_type": type(e).__name__,
            "message": str(e),
            "errno": None,
            "host": None,
            "port": None,
            "url": self._masked_ws_url
        }

        # Extract OSError details (includes connection errors)
        if isinstance(e, OSError):
            details["errno"] = getattr(e, "errno", None)

            # Parse connection details from error message
            error_str = str(e)

            # Extract errno description (e.g., "[Errno 113] Connect call failed")
            if "[Errno" in error_str and "]" in error_str:
                errno_desc = error_str[error_str.index("["):error_str.index("]")+1]
                details["message"] = error_str

            # Extract host and port from error message
            # Format: "Connect call failed ('129.27.161.109', 443)"
            if "(" in error_str and ")" in error_str:
                try:
                    # Find the tuple in the error message
                    start_idx = error_str.rfind("(")
                    end_idx = error_str.rfind(")")
                    tuple_str = error_str[start_idx+1:end_idx]

                    # Parse host and port
                    parts = tuple_str.split(",")
                    if len(parts) >= 2:
                        details["host"] = parts[0].strip().strip("'\"")
                        details["port"] = parts[1].strip().strip("'\"")
                except:
                    pass

        # Extract WebSocketException details
        elif isinstance(e, WebSocketException):
            # WebSocket specific error details
            if hasattr(e, "status_code"):
                details["status_code"] = e.status_code
            if hasattr(e, "headers"):
                details["headers"] = dict(e.headers) if e.headers else None

        # Build detailed message
        if details["errno"]:
            details["message"] = f"[Errno {details['errno']}] {details['message']}"
        if details["host"] and details["port"]:
            details["message"] = f"{details['message']} - Target: {details['host']}:{details['port']}"

        return details
