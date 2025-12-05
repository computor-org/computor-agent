"""
Git credentials store for managing access tokens.

This module provides a mapping system for associating Git URLs
(hosts, groups, projects) with access tokens for authentication.
"""

import os
import json
from enum import Enum
from pathlib import Path
from typing import Optional, Union
from urllib.parse import urlparse

import yaml
from pydantic import BaseModel, Field, SecretStr

from computor_agent.git.auth import GitCredentials, GitProvider


class CredentialScope(str, Enum):
    """Scope level for credential matching (auto-inferred from pattern)."""

    HOST = "host"  # Matches entire host (e.g., gitlab.example.com)
    GROUP = "group"  # Matches a group/organization (e.g., gitlab.example.com/mygroup)
    PROJECT = "project"  # Matches a specific project (e.g., gitlab.example.com/mygroup/myrepo)


def _infer_scope(pattern: str) -> CredentialScope:
    """
    Infer the credential scope from a URL pattern.

    - No path or just "/" -> HOST
    - One path segment (e.g., /group) -> GROUP
    - Two+ path segments (e.g., /group/repo) -> PROJECT
    """
    parsed = urlparse(pattern)
    path = parsed.path.rstrip("/")

    # Remove .git suffix
    if path.endswith(".git"):
        path = path[:-4]

    # Count non-empty path segments
    segments = [s for s in path.split("/") if s]

    if len(segments) == 0:
        return CredentialScope.HOST
    elif len(segments) == 1:
        return CredentialScope.GROUP
    else:
        return CredentialScope.PROJECT


class CredentialMapping(BaseModel):
    """
    A mapping between a URL pattern and credentials.

    Scope is automatically inferred from the pattern:
    - "https://gitlab.example.com" -> HOST (matches all repos)
    - "https://gitlab.example.com/mygroup" -> GROUP (matches repos in group)
    - "https://gitlab.example.com/mygroup/myrepo" -> PROJECT (exact match)

    Example:
        ```python
        # Host-level credential (auto-detected from pattern)
        mapping = CredentialMapping(
            pattern="https://gitlab.example.com",
            token="glpat-xxxx",
        )

        # Group-level credential (auto-detected)
        mapping = CredentialMapping(
            pattern="https://gitlab.example.com/course-submissions",
            token="glpat-yyyy",
        )
        ```
    """

    pattern: str = Field(
        description="URL pattern to match (host, group, or project URL)"
    )
    token: SecretStr = Field(
        description="Access token for authentication"
    )
    username: Optional[str] = Field(
        default=None,
        description="Username (optional, auto-detected for known providers)"
    )
    provider: GitProvider = Field(
        default=GitProvider.GENERIC,
        description="Git provider type (auto-detected if not specified)"
    )
    description: Optional[str] = Field(
        default=None,
        description="Optional human-readable description"
    )

    @property
    def scope(self) -> CredentialScope:
        """Get the scope (auto-inferred from pattern)."""
        return _infer_scope(self.pattern)

    def get_token(self) -> str:
        """Get the token as a plain string."""
        return self.token.get_secret_value()

    def to_git_credentials(self) -> GitCredentials:
        """Convert to GitCredentials for use with GitRepository."""
        return GitCredentials(
            token=self.token,
            username=self.username,
            provider=self.provider,
        )

    def matches(self, url: str) -> bool:
        """
        Check if this mapping matches the given URL.

        Args:
            url: Git repository URL to check

        Returns:
            True if this mapping should apply to the URL
        """
        parsed_url = urlparse(url.lower())
        parsed_pattern = urlparse(self.pattern.lower())

        # Must match scheme (http/https)
        if parsed_pattern.scheme and parsed_url.scheme != parsed_pattern.scheme:
            # Allow http pattern to match https
            if not (parsed_pattern.scheme == "http" and parsed_url.scheme == "https"):
                return False

        # Must match host
        if parsed_pattern.hostname != parsed_url.hostname:
            return False

        # Get auto-inferred scope
        scope = self.scope

        # For host scope, we're done
        if scope == CredentialScope.HOST:
            return True

        # For group/project scope, check path prefix
        pattern_path = parsed_pattern.path.rstrip("/")
        url_path = parsed_url.path.rstrip("/")

        # Remove .git suffix for comparison
        if url_path.endswith(".git"):
            url_path = url_path[:-4]
        if pattern_path.endswith(".git"):
            pattern_path = pattern_path[:-4]

        if scope == CredentialScope.PROJECT:
            # Exact match required
            return url_path == pattern_path

        # Group scope: URL path must start with pattern path
        return url_path.startswith(pattern_path + "/") or url_path == pattern_path

    def match_score(self, url: str) -> int:
        """
        Calculate match score for prioritization.

        Higher scores indicate more specific matches (based on path depth).

        Returns:
            Score (0 = no match, higher = more specific)
        """
        if not self.matches(url):
            return 0

        # Score based on path depth - more specific paths score higher
        parsed_pattern = urlparse(self.pattern)
        path = parsed_pattern.path.rstrip("/")
        if path.endswith(".git"):
            path = path[:-4]

        path_depth = len([p for p in path.split("/") if p])

        # Base score of 1 (for host match) + path depth
        return 1 + path_depth


class GitCredentialsStore:
    """
    Store for managing Git credentials mapped to URL patterns.

    Scope is automatically inferred from the pattern:
    - Host pattern (no path): matches all repos on the host
    - Group pattern (one path segment): matches repos in that group
    - Project pattern (two+ segments): matches exact repository

    More specific patterns always take precedence.

    Example:
        ```python
        store = GitCredentialsStore()

        # Host-level (matches all repos on gitlab.example.com)
        store.add(
            pattern="https://gitlab.example.com",
            token="glpat-default",
        )

        # Group-level (matches repos in course-2024 group)
        store.add(
            pattern="https://gitlab.example.com/course-2024",
            token="glpat-course",
        )

        # Get credentials for a URL (will use group token - more specific)
        creds = store.get_credentials(
            "https://gitlab.example.com/course-2024/student-repo.git"
        )

        # Load from file
        store = GitCredentialsStore.from_file("~/.computor/credentials.yaml")
        ```
    """

    def __init__(self, mappings: Optional[list[CredentialMapping]] = None):
        """
        Initialize the credentials store.

        Args:
            mappings: Initial list of credential mappings
        """
        self._mappings: list[CredentialMapping] = mappings or []

    def add(
        self,
        pattern: str,
        token: str,
        *,
        username: Optional[str] = None,
        provider: GitProvider = GitProvider.GENERIC,
        description: Optional[str] = None,
    ) -> CredentialMapping:
        """
        Add a credential mapping.

        Scope is automatically inferred from the pattern:
        - "https://host.com" -> matches all repos on host
        - "https://host.com/group" -> matches repos in group
        - "https://host.com/group/repo" -> matches exact repo

        Args:
            pattern: URL pattern to match
            token: Access token
            username: Optional username
            provider: Git provider type (auto-detected from hostname if not set)
            description: Optional human-readable description

        Returns:
            The created CredentialMapping
        """
        mapping = CredentialMapping(
            pattern=pattern,
            token=SecretStr(token),
            username=username,
            provider=provider,
            description=description,
        )
        self._mappings.append(mapping)
        return mapping

    def remove(self, pattern: str) -> bool:
        """
        Remove a credential mapping by pattern.

        Args:
            pattern: URL pattern to remove

        Returns:
            True if a mapping was removed
        """
        original_count = len(self._mappings)
        self._mappings = [m for m in self._mappings if m.pattern != pattern]
        return len(self._mappings) < original_count

    def get_credentials(self, url: str) -> Optional[GitCredentials]:
        """
        Get credentials for a Git URL.

        Finds the most specific matching credential mapping.

        Args:
            url: Git repository URL

        Returns:
            GitCredentials if a match is found, None otherwise
        """
        mapping = self.get_mapping(url)
        if mapping:
            return mapping.to_git_credentials()
        return None

    def get_mapping(self, url: str) -> Optional[CredentialMapping]:
        """
        Get the best matching credential mapping for a URL.

        Args:
            url: Git repository URL

        Returns:
            Best matching CredentialMapping, or None
        """
        best_match = None
        best_score = 0

        for mapping in self._mappings:
            score = mapping.match_score(url)
            if score > best_score:
                best_score = score
                best_match = mapping

        return best_match

    def list_mappings(self) -> list[CredentialMapping]:
        """Get all credential mappings."""
        return self._mappings.copy()

    @classmethod
    def from_file(cls, path: Union[str, Path]) -> "GitCredentialsStore":
        """
        Load credentials store from a YAML or JSON file.

        File format (YAML):
            ```yaml
            credentials:
              # Host-level (no path = matches all repos)
              - pattern: https://gitlab.example.com
                token: glpat-xxxx

              # Group-level (one path segment = matches group)
              - pattern: https://gitlab.example.com/courses
                token: glpat-yyyy

              # Project-level (two segments = exact match)
              - pattern: https://github.com/org/repo
                token: ghp_xxxx

              # Optional fields
              - pattern: https://git.internal.com
                token: token123
                provider: gitlab
                username: deploy-bot
                description: Internal server
            ```

        Args:
            path: Path to credentials file

        Returns:
            Loaded GitCredentialsStore
        """
        path = Path(path).expanduser().resolve()

        if not path.exists():
            raise FileNotFoundError(f"Credentials file not found: {path}")

        content = path.read_text()

        if path.suffix in (".yaml", ".yml"):
            data = yaml.safe_load(content)
        elif path.suffix == ".json":
            data = json.loads(content)
        else:
            # Try YAML first, then JSON
            try:
                data = yaml.safe_load(content)
            except Exception:
                data = json.loads(content)

        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict) -> "GitCredentialsStore":
        """
        Create credentials store from a dictionary.

        Args:
            data: Dictionary with 'credentials' key containing list of mappings

        Returns:
            GitCredentialsStore instance
        """
        store = cls()

        credentials_data = data.get("credentials", [])

        for cred in credentials_data:
            # Parse provider (optional)
            provider_str = cred.get("provider", "generic").lower()
            try:
                provider = GitProvider(provider_str)
            except ValueError:
                provider = GitProvider.GENERIC

            store.add(
                pattern=cred["pattern"],
                token=cred["token"],
                username=cred.get("username"),
                provider=provider,
                description=cred.get("description"),
            )

        return store

    def to_dict(self, include_tokens: bool = False) -> dict:
        """
        Export credentials store to a dictionary.

        Args:
            include_tokens: If True, include actual tokens (DANGER!)
                          If False, tokens are masked

        Returns:
            Dictionary representation
        """
        credentials = []

        for mapping in self._mappings:
            cred = {
                "pattern": mapping.pattern,
                "token": mapping.get_token() if include_tokens else "***",
            }
            # Only include non-default provider
            if mapping.provider != GitProvider.GENERIC:
                cred["provider"] = mapping.provider.value
            if mapping.username:
                cred["username"] = mapping.username
            if mapping.description:
                cred["description"] = mapping.description

            credentials.append(cred)

        return {"credentials": credentials}

    def save(self, path: Union[str, Path], format: str = "yaml") -> None:
        """
        Save credentials store to a file.

        WARNING: This saves actual tokens to disk. Ensure proper file permissions.

        Args:
            path: Output file path
            format: Output format ('yaml' or 'json')
        """
        path = Path(path).expanduser().resolve()

        # Create parent directories
        path.parent.mkdir(parents=True, exist_ok=True)

        data = self.to_dict(include_tokens=True)

        if format == "yaml":
            content = yaml.dump(data, default_flow_style=False, sort_keys=False)
        else:
            content = json.dumps(data, indent=2)

        # Write with restricted permissions (owner only)
        path.write_text(content)
        os.chmod(path, 0o600)

    @classmethod
    def from_env(cls, prefix: str = "GIT_CRED_") -> "GitCredentialsStore":
        """
        Load credentials from environment variables.

        Environment variable format:
            GIT_CRED_0_PATTERN=https://gitlab.example.com
            GIT_CRED_0_TOKEN=glpat-xxxx

            GIT_CRED_1_PATTERN=https://github.com/org
            GIT_CRED_1_TOKEN=ghp_xxxx

        Optional variables:
            GIT_CRED_0_PROVIDER=gitlab
            GIT_CRED_0_USERNAME=oauth2

        Args:
            prefix: Environment variable prefix

        Returns:
            GitCredentialsStore with credentials from environment
        """
        store = cls()
        index = 0

        while True:
            pattern_key = f"{prefix}{index}_PATTERN"
            token_key = f"{prefix}{index}_TOKEN"

            pattern = os.environ.get(pattern_key)
            token = os.environ.get(token_key)

            if not pattern or not token:
                break

            provider_str = os.environ.get(f"{prefix}{index}_PROVIDER", "generic")
            username = os.environ.get(f"{prefix}{index}_USERNAME")

            try:
                provider = GitProvider(provider_str.lower())
            except ValueError:
                provider = GitProvider.GENERIC

            store.add(
                pattern=pattern,
                token=token,
                username=username,
                provider=provider,
            )

            index += 1

        return store

    def __len__(self) -> int:
        return len(self._mappings)

    def __repr__(self) -> str:
        return f"GitCredentialsStore(mappings={len(self._mappings)})"
