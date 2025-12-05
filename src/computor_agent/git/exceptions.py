"""
Git-specific exceptions.

This module defines exceptions that can occur during Git operations.
"""

from typing import Any, Optional


class GitError(Exception):
    """Base exception for all Git-related errors."""

    def __init__(
        self,
        message: str,
        *,
        command: Optional[str] = None,
        return_code: Optional[int] = None,
        stderr: Optional[str] = None,
        repo_path: Optional[str] = None,
    ):
        super().__init__(message)
        self.message = message
        self.command = command
        self.return_code = return_code
        self.stderr = stderr
        self.repo_path = repo_path

    def __str__(self) -> str:
        parts = [self.message]
        if self.command:
            parts.append(f"command='{self.command}'")
        if self.return_code is not None:
            parts.append(f"return_code={self.return_code}")
        return " ".join(parts)


class RepositoryNotFoundError(GitError):
    """Raised when the repository does not exist or is not a valid Git repo."""

    pass


class CloneError(GitError):
    """Raised when cloning a repository fails."""

    pass


class CheckoutError(GitError):
    """Raised when checking out a branch or commit fails."""

    pass


class CommitError(GitError):
    """Raised when creating a commit fails."""

    pass


class PushError(GitError):
    """Raised when pushing to remote fails."""

    pass


class PullError(GitError):
    """Raised when pulling from remote fails."""

    pass


class FetchError(GitError):
    """Raised when fetching from remote fails."""

    pass


class MergeError(GitError):
    """Raised when merging fails (including conflicts)."""

    def __init__(
        self,
        message: str,
        *,
        conflicting_files: Optional[list[str]] = None,
        **kwargs: Any,
    ):
        super().__init__(message, **kwargs)
        self.conflicting_files = conflicting_files or []


class StashError(GitError):
    """Raised when stash operations fail."""

    pass


class BranchError(GitError):
    """Raised when branch operations fail."""

    pass


class RemoteError(GitError):
    """Raised when remote operations fail."""

    pass


class DiffError(GitError):
    """Raised when diff operations fail."""

    pass


class InvalidRefError(GitError):
    """Raised when a reference (branch, tag, commit) is invalid."""

    pass
