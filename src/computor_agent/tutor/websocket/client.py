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
    WSPong,
    WSTypingStart,
    WSTypingStop,
)

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
    ):
        """
        Initialize the WebSocket client.

        Args:
            base_url: Backend API base URL (http:// or https://)
            token: Authentication token (Bearer token)
            reconnect_delay: Initial delay between reconnection attempts (seconds)
            max_reconnect_attempts: Maximum number of reconnection attempts
        """
        # Convert http(s) to ws(s)
        ws_url = base_url.replace("https://", "wss://").replace("http://", "ws://")
        self.ws_url = f"{ws_url}/ws?token={token}"

        self._reconnect_delay = reconnect_delay
        self._max_reconnect_attempts = max_reconnect_attempts

        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._connected = False
        self._reconnect_count = 0

    @property
    def is_connected(self) -> bool:
        """Check if WebSocket is currently connected."""
        return self._connected and self._ws is not None

    async def connect(self) -> None:
        """
        Connect to the WebSocket server.

        Raises:
            WebSocketConnectionError: If connection fails after max attempts
        """
        while self._reconnect_count < self._max_reconnect_attempts:
            try:
                logger.info(f"Connecting to WebSocket: {self._mask_url(self.ws_url)}")
                self._ws = await websockets.connect(
                    self.ws_url,
                    ping_interval=30,
                    ping_timeout=10,
                )
                self._connected = True
                self._reconnect_count = 0
                logger.info("WebSocket connected successfully")
                return

            except (WebSocketException, OSError) as e:
                self._reconnect_count += 1
                delay = self._reconnect_delay * (2 ** (self._reconnect_count - 1))
                delay = min(delay, 60.0)  # Cap at 60 seconds

                logger.warning(
                    f"WebSocket connection failed ({e}), "
                    f"attempt {self._reconnect_count}/{self._max_reconnect_attempts}, "
                    f"retrying in {delay:.1f}s"
                )

                if self._reconnect_count >= self._max_reconnect_attempts:
                    raise WebSocketConnectionError(
                        f"Failed to connect after {self._max_reconnect_attempts} attempts: {e}"
                    ) from e

                await asyncio.sleep(delay)

    async def disconnect(self) -> None:
        """Disconnect from the WebSocket server."""
        self._connected = False
        if self._ws:
            try:
                await self._ws.close()
                logger.info("WebSocket disconnected")
            except Exception as e:
                logger.warning(f"Error closing WebSocket: {e}")
            finally:
                self._ws = None

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

        Yields parsed JSON events. Handles ping/pong automatically.

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

                    yield event

                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse WebSocket message: {e}")
                    continue

        except ConnectionClosed as e:
            logger.warning(f"WebSocket connection closed: {e}")
            self._connected = False
            raise WebSocketError(f"Connection closed: {e}") from e

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
