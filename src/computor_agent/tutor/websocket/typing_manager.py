"""
Typing indicator manager for WebSocket communication.

Manages typing indicators with automatic TTL refresh to keep the indicator
active during long-running operations (e.g., LLM processing).
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from computor_agent.tutor.websocket.client import ComputorWebSocket

logger = logging.getLogger(__name__)


class TypingManager:
    """
    Manages typing indicators with automatic TTL refresh.

    The server auto-expires typing indicators after 5 seconds, so this manager
    sends periodic refresh signals (every 4 seconds by default) to keep the
    indicator active during long-running operations.

    Usage:
        manager = TypingManager(ws)

        # Using context manager (recommended)
        async with manager.typing("submission_group:123"):
            await process_message()  # Typing indicator stays active

        # Manual control
        await manager.start_typing("submission_group:123")
        await process_message()
        await manager.stop_typing("submission_group:123")
    """

    def __init__(
        self,
        ws: "ComputorWebSocket",
        refresh_interval: float = 4.0,
    ):
        """
        Initialize the typing manager.

        Args:
            ws: WebSocket client instance
            refresh_interval: Interval between typing refresh signals (seconds).
                              Should be less than server's 5s TTL.
        """
        self._ws = ws
        self._refresh_interval = refresh_interval

        # Track active typing channels and their refresh tasks
        self._active_channels: dict[str, asyncio.Task] = {}

    async def start_typing(self, channel: str) -> None:
        """
        Start typing indicator for a channel.

        Sends initial typing:start and starts a background task to
        periodically refresh the indicator.

        Args:
            channel: Channel to show typing in (e.g., "submission_group:123")
        """
        # Stop existing typing for this channel if any
        if channel in self._active_channels:
            await self.stop_typing(channel)

        # Send initial typing start
        await self._ws.send_typing_start(channel)

        # Start refresh task
        task = asyncio.create_task(self._refresh_loop(channel))
        self._active_channels[channel] = task
        logger.debug(f"Started typing indicator for {channel}")

    async def stop_typing(self, channel: str) -> None:
        """
        Stop typing indicator for a channel.

        Cancels the refresh task and sends typing:stop.

        Args:
            channel: Channel to stop typing in
        """
        # Cancel refresh task if exists
        if channel in self._active_channels:
            task = self._active_channels.pop(channel)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # Send typing stop
        await self._ws.send_typing_stop(channel)
        logger.debug(f"Stopped typing indicator for {channel}")

    async def stop_all(self) -> None:
        """Stop all active typing indicators."""
        channels = list(self._active_channels.keys())
        for channel in channels:
            await self.stop_typing(channel)

    @asynccontextmanager
    async def typing(self, channel: str):
        """
        Context manager for typing indicator.

        Automatically starts typing when entering and stops when exiting,
        even if an exception occurs.

        Usage:
            async with manager.typing("submission_group:123"):
                await long_running_operation()

        Args:
            channel: Channel to show typing in
        """
        await self.start_typing(channel)
        try:
            yield
        finally:
            await self.stop_typing(channel)

    async def _refresh_loop(self, channel: str) -> None:
        """
        Background task that periodically refreshes typing indicator.

        Args:
            channel: Channel to refresh typing for
        """
        try:
            while True:
                await asyncio.sleep(self._refresh_interval)
                # Re-send typing start to refresh TTL
                await self._ws.send_typing_start(channel)
                logger.debug(f"Refreshed typing indicator for {channel}")
        except asyncio.CancelledError:
            # Task cancelled - this is expected when stop_typing is called
            pass
        except Exception as e:
            logger.warning(f"Error in typing refresh loop for {channel}: {e}")

    @property
    def active_channels(self) -> list[str]:
        """Get list of channels with active typing indicators."""
        return list(self._active_channels.keys())
