"""
Git interface for AI agents.

This module provides a high-level Python API for Git operations,
designed for use by AI agents to analyze and manipulate repositories.

Example:
    ```python
    from computor_agent.git import GitRepository, GitCredentials

    # Open existing repository
    repo = GitRepository("/path/to/repo")

    # Get status
    status = repo.status()
    print(f"On branch: {status.branch}")
    print(f"Is clean: {status.is_clean}")

    # View commits
    for commit in repo.log(limit=5):
        print(f"{commit.short_sha}: {commit.subject}")

    # Get diff
    diff = repo.diff()
    print(f"Files changed: {diff.files_changed}")

    # Clone a public repository
    repo = GitRepository.clone(
        "https://github.com/user/repo.git",
        "/tmp/repo",
        depth=1,
    )

    # Clone a private repository with token
    creds = GitCredentials(token="ghp_xxxx")
    repo = GitRepository.clone(
        "https://github.com/user/private-repo.git",
        "/tmp/private-repo",
        credentials=creds,
    )
    ```
"""

from computor_agent.git.auth import (
    GitCredentials,
    GitProvider,
    inject_credentials,
    mask_credentials,
    strip_credentials,
)
from computor_agent.git.exceptions import (
    BranchError,
    CheckoutError,
    CloneError,
    CommitError,
    DiffError,
    FetchError,
    GitError,
    InvalidRefError,
    MergeError,
    PullError,
    PushError,
    RemoteError,
    RepositoryNotFoundError,
    StashError,
)
from computor_agent.git.models import (
    Author,
    Branch,
    Commit,
    Diff,
    DiffHunk,
    FileDiff,
    FileChange,
    FileStatus,
    Remote,
    RepoStatus,
    Tag,
)
from computor_agent.git.repository import GitRepository

__all__ = [
    # Main class
    "GitRepository",
    # Authentication
    "GitCredentials",
    "GitProvider",
    "inject_credentials",
    "mask_credentials",
    "strip_credentials",
    # Models
    "Author",
    "Branch",
    "Commit",
    "Diff",
    "DiffHunk",
    "FileDiff",
    "FileChange",
    "FileStatus",
    "Remote",
    "RepoStatus",
    "Tag",
    # Exceptions
    "GitError",
    "RepositoryNotFoundError",
    "CloneError",
    "CheckoutError",
    "CommitError",
    "PushError",
    "PullError",
    "FetchError",
    "MergeError",
    "StashError",
    "BranchError",
    "RemoteError",
    "DiffError",
    "InvalidRefError",
]
