"""WebSocket authentication helpers.

The WebSocket handshake needs the same credential the HTTP client uses, which
computor-client exposes as ``client.access_token`` /
``client.refresh_access_token()``.
"""

import logging
from typing import Awaitable, Callable, Optional

logger = logging.getLogger(__name__)


async def get_ws_token(client, backend_config) -> Optional[str]:
    """Resolve the token used for the WebSocket handshake.

    API-token auth uses the static token; SSO auth borrows the bearer token
    from the client session.
    """
    token = backend_config.get_api_token()
    if token:
        return token
    token = client.access_token
    if token:
        logger.info("Using session access token for WebSocket authentication")
    return token


def make_token_provider(
    client, backend_config
) -> Callable[[], Awaitable[Optional[str]]]:
    """Build the refresh callback the scheduler calls before each reconnect."""

    async def provide_fresh_token() -> Optional[str]:
        # For API token auth, the token is static
        api_token = backend_config.get_api_token()
        if api_token:
            return api_token
        # SSO bearer auth: rotate via the refresh token. There is no
        # username/password fallback — the API has no such endpoint.
        new_token = await client.refresh_access_token()
        if not new_token:
            logger.error(
                "Token refresh failed and no API token is configured; "
                "the WebSocket cannot reconnect until a new session token is set."
            )
        return new_token

    return provide_fresh_token
