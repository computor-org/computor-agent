"""
Git data models.

This module defines Pydantic models for representing Git data structures.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class FileStatus(str, Enum):
    """Status of a file in the working tree."""

    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"
    RENAMED = "renamed"
    COPIED = "copied"
    UNTRACKED = "untracked"
    IGNORED = "ignored"
    UNMERGED = "unmerged"


class FileChange(BaseModel):
    """Represents a changed file in the working tree or index."""

    path: str = Field(description="File path relative to repo root")
    status: FileStatus = Field(description="Status of the file")
    staged: bool = Field(default=False, description="Whether the change is staged")
    old_path: Optional[str] = Field(
        default=None, description="Original path for renamed/copied files"
    )

    def __str__(self) -> str:
        prefix = "staged" if self.staged else "unstaged"
        if self.old_path:
            return f"{prefix} {self.status.value}: {self.old_path} -> {self.path}"
        return f"{prefix} {self.status.value}: {self.path}"


class RepoStatus(BaseModel):
    """Status of a Git repository."""

    branch: Optional[str] = Field(default=None, description="Current branch name")
    commit: Optional[str] = Field(default=None, description="Current commit SHA")
    is_detached: bool = Field(default=False, description="Whether HEAD is detached")
    is_clean: bool = Field(default=True, description="Whether working tree is clean")
    staged: list[FileChange] = Field(default_factory=list, description="Staged changes")
    unstaged: list[FileChange] = Field(default_factory=list, description="Unstaged changes")
    untracked: list[str] = Field(default_factory=list, description="Untracked files")
    ahead: int = Field(default=0, description="Commits ahead of upstream")
    behind: int = Field(default=0, description="Commits behind upstream")

    @property
    def has_changes(self) -> bool:
        """Check if there are any changes (staged, unstaged, or untracked)."""
        return bool(self.staged or self.unstaged or self.untracked)


class Author(BaseModel):
    """Git author/committer information."""

    name: str = Field(description="Author name")
    email: str = Field(description="Author email")


class Commit(BaseModel):
    """Represents a Git commit."""

    sha: str = Field(description="Full commit SHA")
    short_sha: str = Field(description="Short commit SHA (7 chars)")
    message: str = Field(description="Commit message")
    author: Author = Field(description="Author information")
    committer: Author = Field(description="Committer information")
    authored_date: datetime = Field(description="Author date")
    committed_date: datetime = Field(description="Commit date")
    parent_shas: list[str] = Field(default_factory=list, description="Parent commit SHAs")

    @property
    def subject(self) -> str:
        """Get the first line of the commit message."""
        return self.message.split("\n", 1)[0]

    @property
    def body(self) -> Optional[str]:
        """Get the commit message body (after first line)."""
        parts = self.message.split("\n", 1)
        return parts[1].strip() if len(parts) > 1 else None

    @property
    def is_merge(self) -> bool:
        """Check if this is a merge commit."""
        return len(self.parent_shas) > 1


class Branch(BaseModel):
    """Represents a Git branch."""

    name: str = Field(description="Branch name")
    commit_sha: str = Field(description="Commit SHA the branch points to")
    is_current: bool = Field(default=False, description="Whether this is the current branch")
    is_remote: bool = Field(default=False, description="Whether this is a remote branch")
    tracking: Optional[str] = Field(
        default=None, description="Remote tracking branch (e.g., origin/main)"
    )
    ahead: int = Field(default=0, description="Commits ahead of tracking branch")
    behind: int = Field(default=0, description="Commits behind tracking branch")


class Remote(BaseModel):
    """Represents a Git remote."""

    name: str = Field(description="Remote name (e.g., origin)")
    url: str = Field(description="Remote URL")
    fetch_url: Optional[str] = Field(default=None, description="Fetch URL if different")
    push_url: Optional[str] = Field(default=None, description="Push URL if different")


class DiffHunk(BaseModel):
    """Represents a diff hunk."""

    old_start: int = Field(description="Starting line in old file")
    old_count: int = Field(description="Number of lines in old file")
    new_start: int = Field(description="Starting line in new file")
    new_count: int = Field(description="Number of lines in new file")
    content: str = Field(description="Hunk content with +/- prefixes")


class FileDiff(BaseModel):
    """Represents diff for a single file."""

    path: str = Field(description="File path")
    old_path: Optional[str] = Field(default=None, description="Old path for renames")
    status: FileStatus = Field(description="Change type")
    hunks: list[DiffHunk] = Field(default_factory=list, description="Diff hunks")
    is_binary: bool = Field(default=False, description="Whether file is binary")
    additions: int = Field(default=0, description="Number of added lines")
    deletions: int = Field(default=0, description="Number of deleted lines")

    @property
    def patch(self) -> str:
        """Get the full patch content."""
        return "\n".join(h.content for h in self.hunks)


class Diff(BaseModel):
    """Represents a complete diff (possibly multiple files)."""

    files: list[FileDiff] = Field(default_factory=list, description="Changed files")
    stats: str = Field(default="", description="Diff stats summary")

    @property
    def total_additions(self) -> int:
        """Total lines added."""
        return sum(f.additions for f in self.files)

    @property
    def total_deletions(self) -> int:
        """Total lines deleted."""
        return sum(f.deletions for f in self.files)

    @property
    def files_changed(self) -> int:
        """Number of files changed."""
        return len(self.files)


class Tag(BaseModel):
    """Represents a Git tag."""

    name: str = Field(description="Tag name")
    commit_sha: str = Field(description="Commit SHA the tag points to")
    message: Optional[str] = Field(default=None, description="Tag message (annotated tags)")
    tagger: Optional[Author] = Field(default=None, description="Tagger info (annotated tags)")
    is_annotated: bool = Field(default=False, description="Whether tag is annotated")
