"""WebSocket authentication helpers.

This module is the only place allowed to touch ComputorClient's private
``_auth_provider``: computor-client does not expose a public token API yet,
so the private access is centralized here as the single change point for
when it does.
"""

import logging
from typing import Awaitable, Callable, Optional

logger = logging.getLogger(__name__)


async def get_ws_token(client, backend_config) -> Optional[str]:
    """Resolve the token used for the WebSocket handshake.

    API-token auth uses the static token; username/password auth borrows the
    access token from the authenticated client session.
    """
    token = backend_config.get_api_token()
    if token:
        return token
    token = await client._auth_provider.get_access_token()
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
        # For username/password auth, refresh via the client
        new_token = await client._auth_provider.refresh_token()
        if new_token:
            return new_token
        # Refresh failed — try re-login
        try:
            await client.login(
                username=backend_config.username,
                password=backend_config.get_password(),
            )
            return await client._auth_provider.get_access_token()
        except Exception as e:
            logger.error(f"Re-login failed during token refresh: {e}")
            return None

    return provide_fresh_token
