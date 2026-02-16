"""
WebSocket client for Computor backend.

Provides a wrapper around the websockets library with:
- Auto-reconnection with exponential backoff
- Heartbeat/ping-pong handling
- Type-safe message sending using computor_types.websocket DTOs
"""

import asyncio
import json
import logging
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
        reconnect_delay: float = 5.0,
        max_reconnect_attempts: int = 10,
        connect_timeout: float = 30.0,
    ):
        """
        Initialize the WebSocket client.

        Args:
            base_url: Backend API base URL (http:// or https://)
            token: Authentication token (Bearer token)
            reconnect_delay: Initial delay between reconnection attempts (seconds)
            max_reconnect_attempts: Maximum number of reconnection attempts
            connect_timeout: Timeout for connection handshake (seconds)
        """
        # Convert http(s) to ws(s)
        ws_url = base_url.replace("https://", "wss://").replace("http://", "ws://")
        self.ws_url = f"{ws_url}/ws?token={token}"

        self._reconnect_delay = reconnect_delay
        self._max_reconnect_attempts = max_reconnect_attempts
        self._connect_timeout = connect_timeout

        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._connected = False
        self._reconnect_count = 0
        self._user_id: Optional[str] = None
        self._ping_task: Optional[asyncio.Task] = None

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
        Connect to the WebSocket server.

        Waits for the system:connected event and starts the ping loop.

        Raises:
            WebSocketConnectionError: If connection fails after max attempts
        """
        while self._reconnect_count < self._max_reconnect_attempts:
            try:
                logger.info(f"Connecting to WebSocket: {self._mask_url(self.ws_url)}")
                self._ws = await websockets.connect(
                    self.ws_url,
                    ping_interval=None,  # Disable library ping, we handle it ourselves
                    ping_timeout=None,
                    open_timeout=self._connect_timeout,
                    close_timeout=10.0,
                )

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

                self._connected = True
                self._reconnect_count = 0

                # Start ping loop
                self._ping_task = asyncio.create_task(self._ping_loop())

                return

            except asyncio.TimeoutError as e:
                # Handle connection timeout (opening handshake timeout)
                self._reconnect_count += 1
                delay = self._reconnect_delay * (2 ** (self._reconnect_count - 1))
                delay = min(delay, 60.0)

                logger.warning(
                    f"WebSocket connection timed out after {self._connect_timeout}s\n"
                    f"  Target URL: {self._mask_url(self.ws_url)}\n"
                    f"  Attempt: {self._reconnect_count}/{self._max_reconnect_attempts}\n"
                    f"  Next retry in: {delay:.1f}s"
                )

                if self._reconnect_count >= self._max_reconnect_attempts:
                    raise WebSocketConnectionError(
                        f"Connection timed out after {self._max_reconnect_attempts} attempts"
                    ) from e

                await asyncio.sleep(delay)

            except (WebSocketException, OSError) as e:
                self._reconnect_count += 1
                delay = self._reconnect_delay * (2 ** (self._reconnect_count - 1))
                delay = min(delay, 60.0)  # Cap at 60 seconds

                # Extract more detailed error information
                error_details = self._extract_error_details(e)

                logger.warning(
                    f"WebSocket connection failed: {error_details['message']}\n"
                    f"  Error type: {error_details['error_type']}\n"
                    f"  Target URL: {error_details['url']}\n"
                    f"  Attempt: {self._reconnect_count}/{self._max_reconnect_attempts}\n"
                    f"  Next retry in: {delay:.1f}s"
                )

                if self._reconnect_count >= self._max_reconnect_attempts:
                    raise WebSocketConnectionError(
                        f"Failed to connect after {self._max_reconnect_attempts} attempts: {e}"
                    ) from e

                await asyncio.sleep(delay)

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

    async def subscribe(self, channels: list[str]) -> None:
        """
        Subscribe to one or more channels.

        Args:
            channels: List of channel names (e.g., ["course:abc-123"])
        """
        if not self.is_connected:
            raise WebSocketError("Not connected")

        msg = WSChannelSubscribe(type="channel:subscribe", channels=channels)
        await self._send(msg.model_dump())
        logger.info(f"Subscribed to channels: {channels}")

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

    async def _ping_loop(self) -> None:
        """
        Background task that sends periodic pings to keep connection alive.

        Sends system:ping every PING_INTERVAL seconds (25s by default).
        """
        try:
            while self._connected:
                await asyncio.sleep(PING_INTERVAL)
                if self._connected:
                    try:
                        await self.send_ping()
                    except WebSocketError:
                        # Connection lost, exit loop
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
        except ConnectionClosed as e:
            self._connected = False
            raise WebSocketError(f"Connection closed while sending: {e}") from e

    def _mask_url(self, url: str) -> str:
        """Mask the token in URL for logging."""
        if "token=" in url:
            parts = url.split("token=")
            return f"{parts[0]}token=***"
        return url

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
            "url": self._mask_url(self.ws_url)
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
