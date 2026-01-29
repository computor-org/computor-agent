# WebSocket Client Implementation Guide

This document describes the WebSocket behavior and protocol for implementing Python clients that connect to the Computor backend.

## Connection Overview

### Endpoint
```
ws://{host}/ws?token={bearer_token}
```

### Key Characteristics
- **No server-side timeout**: Connections stay open indefinitely
- **Protocol-level ping/pong**: The underlying WebSocket protocol handles keep-alive
- **Long-lived connections supported**: Designed for AI agents and persistent clients (can run for weeks)
- **Dead connection detection**: Server detects dead connections when send operations fail

## Connection Flow

1. Client connects with bearer token as query parameter
2. Server validates token and accepts connection
3. Server sends `system:connected` event with user info
4. Client subscribes to channels via `channel:subscribe`
5. Server validates permissions and confirms with `channel:subscribed`
6. Client/server exchange events
7. Connection closes when client disconnects or send fails

## Client-Side Requirements

### Keep-Alive (Recommended)
While the server has no timeout, clients should implement keep-alive for reliability:

```python
import asyncio
import websockets
import json

PING_INTERVAL = 25  # seconds (matches server's WS_PING_INTERVAL setting)

async def keep_alive(websocket):
    """Send periodic pings to ensure connection health."""
    while True:
        await asyncio.sleep(PING_INTERVAL)
        try:
            await websocket.send(json.dumps({"type": "system:ping"}))
        except:
            break
```

### Reconnection Logic
Clients must implement reconnection logic for production use:

```python
async def connect_with_retry(url, token, max_retries=None):
    """Connect with exponential backoff retry."""
    retry_count = 0
    base_delay = 1.0
    max_delay = 60.0

    while max_retries is None or retry_count < max_retries:
        try:
            websocket = await websockets.connect(f"{url}?token={token}")
            return websocket
        except Exception as e:
            retry_count += 1
            delay = min(base_delay * (2 ** retry_count), max_delay)
            await asyncio.sleep(delay)

    raise ConnectionError("Max retries exceeded")
```

## Message Protocol

### Client -> Server Events

#### Subscribe to Channels
```json
{"type": "channel:subscribe", "channels": ["submission_group:123", "course:456"]}
```

#### Unsubscribe from Channels
```json
{"type": "channel:unsubscribe", "channels": ["submission_group:123"]}
```

#### Typing Indicators
```json
{"type": "typing:start", "channel": "submission_group:123"}
{"type": "typing:stop", "channel": "submission_group:123"}
```

#### Mark Message as Read
```json
{"type": "read:mark", "channel": "submission_group:123", "message_id": "uuid"}
```

#### Keep-Alive Ping
```json
{"type": "system:ping"}
```

### Server -> Client Events

#### Connection Established
```json
{"type": "system:connected", "user_id": "uuid"}
```

#### Subscription Confirmed
```json
{"type": "channel:subscribed", "channels": ["submission_group:123"]}
```

#### Subscription Failed
```json
{"type": "channel:error", "channel": "submission_group:123", "error": "Permission denied"}
```

#### New Message
```json
{
  "type": "message:new",
  "channel": "submission_group:123",
  "data": {
    "id": "uuid",
    "content": "Hello",
    "sender_id": "uuid",
    "created_at": "2025-01-27T10:00:00Z"
  }
}
```

#### Message Updated
```json
{"type": "message:update", "channel": "submission_group:123", "data": {...}}
```

#### Message Deleted
```json
{"type": "message:delete", "channel": "submission_group:123", "data": {"id": "uuid"}}
```

#### Typing Status Update
```json
{
  "type": "typing:update",
  "channel": "submission_group:123",
  "data": {
    "user_id": "uuid",
    "user_name": "John",
    "is_typing": true
  }
}
```

#### Read Receipt (submission_group channels only)
```json
{"type": "read:update", "channel": "submission_group:123", "data": {"message_id": "uuid", "user_id": "uuid"}}
```

#### Keep-Alive Response
```json
{"type": "system:pong"}
```

#### Error
```json
{"type": "system:error", "code": "INVALID_JSON", "message": "Message must be valid JSON"}
```

## Channel Format

Channels follow the pattern: `{scope}:{id}`

| Scope | Description | Example |
|-------|-------------|---------|
| `submission_group` | Messages in a submission group | `submission_group:123` |
| `course_content` | Messages for course content | `course_content:456` |
| `course` | Course-level messages | `course:789` |

## Connection Limits

- **Per-user limit**: 10 connections (configurable via `WS_MAX_CONNECTIONS_PER_USER`)
- **Total server limit**: 10,000 connections (configurable via `WS_MAX_TOTAL_CONNECTIONS`)

When limits are exceeded, server responds with:
```json
{"type": "system:error", "code": "CONNECTION_LIMIT", "message": "..."}
```

## Complete Client Example

```python
import asyncio
import json
import logging
import websockets
from typing import Callable, Optional

logger = logging.getLogger(__name__)

class ComputorWebSocketClient:
    """WebSocket client for Computor backend."""

    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.replace("http", "ws")
        self.token = token
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.user_id: Optional[str] = None
        self._running = False
        self._handlers: dict[str, Callable] = {}

    def on(self, event_type: str, handler: Callable):
        """Register handler for event type."""
        self._handlers[event_type] = handler

    async def connect(self):
        """Connect to WebSocket server."""
        url = f"{self.base_url}/ws?token={self.token}"
        self.websocket = await websockets.connect(url)
        self._running = True

        # Wait for connected message
        response = await self.websocket.recv()
        data = json.loads(response)
        if data.get("type") == "system:connected":
            self.user_id = data.get("user_id")
            logger.info(f"Connected as user {self.user_id}")

        return self

    async def subscribe(self, channels: list[str]):
        """Subscribe to channels."""
        await self.send({"type": "channel:subscribe", "channels": channels})

    async def unsubscribe(self, channels: list[str]):
        """Unsubscribe from channels."""
        await self.send({"type": "channel:unsubscribe", "channels": channels})

    async def send(self, data: dict):
        """Send message to server."""
        if self.websocket:
            await self.websocket.send(json.dumps(data))

    async def start_typing(self, channel: str):
        """Start typing indicator."""
        await self.send({"type": "typing:start", "channel": channel})

    async def stop_typing(self, channel: str):
        """Stop typing indicator."""
        await self.send({"type": "typing:stop", "channel": channel})

    async def mark_read(self, channel: str, message_id: str):
        """Mark message as read."""
        await self.send({"type": "read:mark", "channel": channel, "message_id": message_id})

    async def _ping_loop(self):
        """Send periodic pings."""
        while self._running:
            await asyncio.sleep(25)
            try:
                await self.send({"type": "system:ping"})
            except:
                break

    async def _receive_loop(self):
        """Receive and dispatch messages."""
        while self._running:
            try:
                message = await self.websocket.recv()
                data = json.loads(message)
                event_type = data.get("type", "")

                if event_type in self._handlers:
                    await self._handlers[event_type](data)
                elif "message:" in event_type or "typing:" in event_type:
                    # Log unhandled events of interest
                    logger.debug(f"Unhandled event: {event_type}")

            except websockets.ConnectionClosed:
                logger.info("Connection closed")
                break
            except Exception as e:
                logger.error(f"Receive error: {e}")
                break

        self._running = False

    async def run(self):
        """Run client with ping and receive loops."""
        await asyncio.gather(
            self._ping_loop(),
            self._receive_loop()
        )

    async def close(self):
        """Close connection."""
        self._running = False
        if self.websocket:
            await self.websocket.close()


# Usage example
async def main():
    client = ComputorWebSocketClient(
        base_url="http://localhost:8000",
        token="your_bearer_token"
    )

    # Register handlers
    @client.on("message:new")
    async def on_message(data):
        print(f"New message: {data}")

    @client.on("typing:update")
    async def on_typing(data):
        print(f"Typing: {data}")

    # Connect and subscribe
    await client.connect()
    await client.subscribe(["submission_group:123"])

    # Run client (blocks until disconnected)
    try:
        await client.run()
    except KeyboardInterrupt:
        await client.close()

if __name__ == "__main__":
    asyncio.run(main())
```

## Server Configuration Reference

| Setting | Default | Description |
|---------|---------|-------------|
| `WS_MAX_CONNECTIONS_PER_USER` | 10 | Max connections per user |
| `WS_MAX_TOTAL_CONNECTIONS` | 10000 | Max total server connections |
| `WS_PRESENCE_TTL` | 60s | User presence tracking TTL |
| `WS_TYPING_TTL` | 5s | Typing indicator auto-expiry |
| `WS_HANDLER_TIMEOUT` | 5s | Server handler timeout |
| `WS_PING_INTERVAL` | 25s | Recommended client ping interval |
| `WS_SEND_TIMEOUT` | 2s | Server send operation timeout |

## Error Codes

| Code | Description |
|------|-------------|
| `AUTH_FAILED` | Token validation failed |
| `CONNECTION_LIMIT` | Connection limit reached |
| `INVALID_JSON` | Message was not valid JSON |
| `PERMISSION_DENIED` | Not allowed to access channel |
| `INVALID_CHANNEL` | Channel format invalid |
