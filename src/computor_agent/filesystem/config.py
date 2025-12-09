"""
Configuration for restricted filesystem access.
"""

from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class FileSystemAccessConfig(BaseModel):
    """
    Configuration for LLM filesystem access restrictions.

    Defines what files and directories the LLM can access,
    with size limits and pattern-based filtering.
    """

    enabled: bool = Field(
        default=True,
        description="Enable filesystem access for LLMs",
    )

    allowed_directories: list[Path] = Field(
        default_factory=list,
        description="Whitelisted directories (resolved to absolute paths)",
    )

    max_file_size_bytes: int = Field(
        default=10_000_000,  # 10 MB
        ge=0,
        description="Maximum file size that can be read (bytes)",
    )

    allowed_extensions: Optional[list[str]] = Field(
        default=None,
        description="Allowed file extensions (None = all allowed). Include the dot, e.g., ['.py', '.js']",
    )

    blocked_patterns: list[str] = Field(
        default_factory=lambda: [
            ".env",
            "credentials",
            "secrets",
            ".ssh",
            ".git/config",
            "id_rsa",
            "id_ed25519",
            ".password",
            "token",
        ],
        description="Filename patterns that are always blocked (case-insensitive)",
    )

    max_search_results: int = Field(
        default=100,
        ge=1,
        le=10000,
        description="Maximum number of search results to return",
    )

    search_timeout_seconds: float = Field(
        default=30.0,
        ge=1.0,
        le=300.0,
        description="Timeout for search operations (seconds)",
    )

    follow_symlinks: bool = Field(
        default=False,
        description="Allow following symbolic links (security risk if enabled)",
    )

    # Write permissions
    allow_write: bool = Field(
        default=False,
        description="Allow write operations (create/modify files and directories)",
    )

    allow_delete: bool = Field(
        default=False,
        description="Allow delete operations (remove files and directories)",
    )

    max_write_size_bytes: int = Field(
        default=1_000_000,  # 1 MB
        ge=0,
        description="Maximum size for files being written (bytes)",
    )

    allowed_write_extensions: Optional[list[str]] = Field(
        default=None,
        description="Allowed extensions for write operations (None = use allowed_extensions)",
    )

    @field_validator("allowed_directories", mode="before")
    @classmethod
    def resolve_directories(cls, v):
        """Resolve all directories to absolute paths."""
        if not v:
            return []
        return [Path(p).expanduser().resolve() for p in v]

    @field_validator("allowed_extensions", mode="before")
    @classmethod
    def normalize_extensions(cls, v):
        """Ensure extensions start with a dot."""
        if v is None:
            return None
        normalized = []
        for ext in v:
            if not ext.startswith("."):
                ext = f".{ext}"
            normalized.append(ext.lower())
        return normalized

    @field_validator("blocked_patterns", mode="before")
    @classmethod
    def lowercase_patterns(cls, v):
        """Convert patterns to lowercase for case-insensitive matching."""
        return [p.lower() for p in v]

    @field_validator("allowed_write_extensions", mode="before")
    @classmethod
    def normalize_write_extensions(cls, v):
        """Ensure write extensions start with a dot."""
        if v is None:
            return None
        normalized = []
        for ext in v:
            if not ext.startswith("."):
                ext = f".{ext}"
            normalized.append(ext.lower())
        return normalized

    def is_path_allowed(self, path: Path) -> tuple[bool, str]:
        """
        Check if a path is allowed based on configuration.

        Args:
            path: Path to check

        Returns:
            Tuple of (is_allowed, reason)
        """
        if not self.enabled:
            return False, "Filesystem access is disabled"

        try:
            resolved = path.expanduser().resolve()
        except (OSError, RuntimeError) as e:
            return False, f"Invalid path: {e}"

        # Check if within allowed directories
        if self.allowed_directories:
            is_within_allowed = any(
                self._is_within_directory(resolved, allowed)
                for allowed in self.allowed_directories
            )
            if not is_within_allowed:
                return False, "Path is not within allowed directories"

        # Check blocked patterns
        path_lower = str(resolved).lower()
        for pattern in self.blocked_patterns:
            if pattern in path_lower:
                return False, f"Path matches blocked pattern: {pattern}"

        # Check allowed extensions
        if self.allowed_extensions is not None:
            ext = resolved.suffix.lower()
            if ext not in self.allowed_extensions:
                return False, f"File extension {ext} not allowed"

        # Check if it's a file (not directory)
        if resolved.exists() and not resolved.is_file():
            if not resolved.is_dir():
                return False, "Path is not a regular file"

        # Check symlinks
        if not self.follow_symlinks and resolved.is_symlink():
            return False, "Symbolic links are not allowed"

        return True, "Path is allowed"

    def _is_within_directory(self, path: Path, directory: Path) -> bool:
        """Check if path is within directory (prevents path traversal)."""
        try:
            path.relative_to(directory)
            return True
        except ValueError:
            return False

    def __repr__(self) -> str:
        """Safe representation."""
        return (
            f"FileSystemAccessConfig("
            f"enabled={self.enabled}, "
            f"allowed_dirs={len(self.allowed_directories)}, "
            f"max_size={self.max_file_size_bytes})"
        )
