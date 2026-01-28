"""
WebSocket support for the Tutor AI Agent.

Provides real-time event handling as an alternative to HTTP polling.
"""

from computor_agent.tutor.websocket.client import (
    ComputorWebSocket,
    WebSocketConnectionError,
    WebSocketError,
)
from computor_agent.tutor.websocket.scheduler import WebSocketScheduler
from computor_agent.tutor.websocket.typing_manager import TypingManager

__all__ = [
    "ComputorWebSocket",
    "WebSocketScheduler",
    "TypingManager",
    "WebSocketError",
    "WebSocketConnectionError",
]
