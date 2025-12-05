"""
Git authentication utilities.

This module provides functions for handling Git authentication,
including injecting tokens into HTTPS URLs for various providers.
"""

import re
from enum import Enum
from typing import Optional
from urllib.parse import urlparse, urlunparse

from pydantic import BaseModel, SecretStr, Field


class GitProvider(str, Enum):
    """Known Git hosting providers."""

    GITHUB = "github"
    GITLAB = "gitlab"
    BITBUCKET = "bitbucket"
    AZURE = "azure"
    GENERIC = "generic"


class GitCredentials(BaseModel):
    """
    Credentials for Git authentication.

    Supports multiple authentication methods:
    - Personal Access Token (PAT)
    - Username + Password/Token
    - OAuth tokens

    Example:
        ```python
        # GitHub PAT
        creds = GitCredentials(token="ghp_xxxx")

        # GitLab with username
        creds = GitCredentials(
            username="oauth2",
            token="glpat-xxxx",
            provider=GitProvider.GITLAB,
        )

        # Generic with username/password
        creds = GitCredentials(
            username="user",
            password="pass",
        )
        ```
    """

    token: Optional[SecretStr] = Field(
        default=None,
        description="Access token (PAT, OAuth token, etc.)",
    )
    username: Optional[str] = Field(
        default=None,
        description="Username for authentication",
    )
    password: Optional[SecretStr] = Field(
        default=None,
        description="Password (prefer token over password)",
    )
    provider: GitProvider = Field(
        default=GitProvider.GENERIC,
        description="Git provider (affects URL format)",
    )

    def get_token(self) -> Optional[str]:
        """Get the token as a plain string."""
        if self.token:
            return self.token.get_secret_value()
        return None

    def get_password(self) -> Optional[str]:
        """Get the password as a plain string."""
        if self.password:
            return self.password.get_secret_value()
        return None


def inject_credentials(url: str, credentials: GitCredentials) -> str:
    """
    Inject credentials into a Git URL.

    Supports HTTPS URLs for GitHub, GitLab, Bitbucket, Azure DevOps,
    and generic Git servers.

    Args:
        url: Original Git URL (HTTPS)
        credentials: Authentication credentials

    Returns:
        URL with embedded credentials

    Example:
        ```python
        # GitHub with PAT
        creds = GitCredentials(token="ghp_xxxx")
        auth_url = inject_credentials(
            "https://github.com/user/repo.git",
            creds,
        )
        # Result: https://ghp_xxxx@github.com/user/repo.git

        # GitLab with username
        creds = GitCredentials(
            username="oauth2",
            token="glpat-xxxx",
            provider=GitProvider.GITLAB,
        )
        auth_url = inject_credentials(
            "https://gitlab.com/user/repo.git",
            creds,
        )
        # Result: https://oauth2:glpat-xxxx@gitlab.com/user/repo.git
        ```
    """
    parsed = urlparse(url)

    # Only inject credentials for HTTPS URLs
    if parsed.scheme not in ("http", "https"):
        return url

    # Build the auth component
    auth = _build_auth_string(credentials, parsed.hostname or "")

    if not auth:
        return url

    # Reconstruct URL with credentials
    # netloc format: user:pass@host:port
    if parsed.port:
        netloc = f"{auth}@{parsed.hostname}:{parsed.port}"
    else:
        netloc = f"{auth}@{parsed.hostname}"

    return urlunparse((
        parsed.scheme,
        netloc,
        parsed.path,
        parsed.params,
        parsed.query,
        parsed.fragment,
    ))


def _build_auth_string(credentials: GitCredentials, hostname: str) -> Optional[str]:
    """
    Build the authentication string for URL injection.

    Different providers have different requirements:
    - GitHub: token alone or "x-access-token:token"
    - GitLab: "oauth2:token" or "username:token"
    - Bitbucket: "x-token-auth:token"
    - Azure: "pat:token"
    - Generic: "username:password" or "username:token"
    """
    token = credentials.get_token()
    password = credentials.get_password()
    username = credentials.username

    # Auto-detect provider from hostname if not specified
    provider = credentials.provider
    if provider == GitProvider.GENERIC:
        provider = _detect_provider(hostname)

    if token:
        if provider == GitProvider.GITHUB:
            # GitHub accepts token alone or with x-access-token username
            if username:
                return f"{username}:{token}"
            return f"x-access-token:{token}"

        elif provider == GitProvider.GITLAB:
            # GitLab uses oauth2 or specific username
            if username:
                return f"{username}:{token}"
            return f"oauth2:{token}"

        elif provider == GitProvider.BITBUCKET:
            # Bitbucket uses x-token-auth
            if username:
                return f"{username}:{token}"
            return f"x-token-auth:{token}"

        elif provider == GitProvider.AZURE:
            # Azure DevOps uses PAT with any username
            if username:
                return f"{username}:{token}"
            return f"pat:{token}"

        else:
            # Generic: use token as password with username
            if username:
                return f"{username}:{token}"
            # Token alone might not work for all servers
            return token

    elif password and username:
        # Username + password authentication
        return f"{username}:{password}"

    elif username:
        # Username only (might prompt for password)
        return username

    return None


def _detect_provider(hostname: str) -> GitProvider:
    """Detect Git provider from hostname."""
    hostname = hostname.lower()

    if "github" in hostname:
        return GitProvider.GITHUB
    elif "gitlab" in hostname:
        return GitProvider.GITLAB
    elif "bitbucket" in hostname:
        return GitProvider.BITBUCKET
    elif "dev.azure.com" in hostname or "visualstudio.com" in hostname:
        return GitProvider.AZURE

    return GitProvider.GENERIC


def strip_credentials(url: str) -> str:
    """
    Remove credentials from a Git URL.

    Useful for logging URLs without exposing secrets.

    Args:
        url: URL possibly containing credentials

    Returns:
        URL with credentials removed

    Example:
        ```python
        clean = strip_credentials("https://token@github.com/user/repo.git")
        # Result: https://github.com/user/repo.git
        ```
    """
    parsed = urlparse(url)

    if not parsed.username:
        return url

    # Reconstruct without credentials
    if parsed.port:
        netloc = f"{parsed.hostname}:{parsed.port}"
    else:
        netloc = parsed.hostname or ""

    return urlunparse((
        parsed.scheme,
        netloc,
        parsed.path,
        parsed.params,
        parsed.query,
        parsed.fragment,
    ))


def mask_credentials(url: str) -> str:
    """
    Mask credentials in a Git URL for safe logging.

    Args:
        url: URL possibly containing credentials

    Returns:
        URL with credentials masked as ***

    Example:
        ```python
        masked = mask_credentials("https://token@github.com/user/repo.git")
        # Result: https://***@github.com/user/repo.git
        ```
    """
    parsed = urlparse(url)

    if not parsed.username:
        return url

    # Reconstruct with masked credentials
    if parsed.port:
        netloc = f"***@{parsed.hostname}:{parsed.port}"
    else:
        netloc = f"***@{parsed.hostname}"

    return urlunparse((
        parsed.scheme,
        netloc,
        parsed.path,
        parsed.params,
        parsed.query,
        parsed.fragment,
    ))
