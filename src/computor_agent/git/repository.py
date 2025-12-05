"""
Git repository interface.

This module provides a high-level Python interface for Git operations,
designed for use by AI agents. It wraps GitPython for convenient access
to repository data and operations.
"""

import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional, Union

from git import Repo, GitCommandError, InvalidGitRepositoryError, NoSuchPathError
from git.objects import Commit as GitCommit

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


class GitRepository:
    """
    High-level interface for Git repository operations.

    This class provides a clean Python API for common Git operations,
    suitable for use by AI agents to analyze and manipulate repositories.

    Example:
        ```python
        # Open existing repository
        repo = GitRepository("/path/to/repo")

        # Get status
        status = repo.status()
        print(f"On branch: {status.branch}")
        print(f"Changed files: {len(status.staged) + len(status.unstaged)}")

        # View recent commits
        for commit in repo.log(limit=5):
            print(f"{commit.short_sha}: {commit.subject}")

        # Get diff
        diff = repo.diff()
        for file in diff.files:
            print(f"{file.status.value}: {file.path}")
        ```
    """

    def __init__(self, path: Union[str, Path]):
        """
        Open a Git repository.

        Args:
            path: Path to the repository root

        Raises:
            RepositoryNotFoundError: If the path is not a valid Git repository
        """
        self.path = Path(path).resolve()

        try:
            self._repo = Repo(self.path)
        except InvalidGitRepositoryError:
            raise RepositoryNotFoundError(
                f"Not a valid Git repository: {self.path}",
                repo_path=str(self.path),
            )
        except NoSuchPathError:
            raise RepositoryNotFoundError(
                f"Path does not exist: {self.path}",
                repo_path=str(self.path),
            )

    @classmethod
    def clone(
        cls,
        url: str,
        path: Union[str, Path],
        *,
        branch: Optional[str] = None,
        depth: Optional[int] = None,
        single_branch: bool = False,
    ) -> "GitRepository":
        """
        Clone a repository from a URL.

        Args:
            url: Repository URL (HTTPS or SSH)
            path: Local path to clone to
            branch: Branch to checkout (default: remote HEAD)
            depth: Create a shallow clone with limited history
            single_branch: Clone only the specified branch

        Returns:
            GitRepository instance for the cloned repo

        Raises:
            CloneError: If cloning fails

        Example:
            ```python
            repo = GitRepository.clone(
                "https://github.com/user/repo.git",
                "/tmp/repo",
                branch="main",
                depth=1,
            )
            ```
        """
        path = Path(path).resolve()

        kwargs = {}
        if branch:
            kwargs["branch"] = branch
        if depth:
            kwargs["depth"] = depth
        if single_branch:
            kwargs["single_branch"] = single_branch

        try:
            Repo.clone_from(url, path, **kwargs)
            return cls(path)
        except GitCommandError as e:
            raise CloneError(
                f"Failed to clone {url}: {e.stderr}",
                command=f"git clone {url}",
                return_code=e.status,
                stderr=e.stderr,
                repo_path=str(path),
            )

    @classmethod
    def init(
        cls,
        path: Union[str, Path],
        *,
        bare: bool = False,
        initial_branch: Optional[str] = None,
    ) -> "GitRepository":
        """
        Initialize a new Git repository.

        Args:
            path: Path for the new repository
            bare: Create a bare repository
            initial_branch: Name for the initial branch (default: git default)

        Returns:
            GitRepository instance for the new repo

        Raises:
            GitError: If initialization fails
        """
        path = Path(path).resolve()
        path.mkdir(parents=True, exist_ok=True)

        try:
            repo = Repo.init(path, bare=bare)
            if initial_branch and not bare:
                # Set the initial branch name
                repo.head.reference = repo.create_head(initial_branch)
            return cls(path)
        except GitCommandError as e:
            raise GitError(
                f"Failed to initialize repository: {e.stderr}",
                command="git init",
                return_code=e.status,
                stderr=e.stderr,
                repo_path=str(path),
            )

    # =========================================================================
    # Status and Info
    # =========================================================================

    def status(self) -> RepoStatus:
        """
        Get the current repository status.

        Returns:
            RepoStatus with branch, changes, and tracking info

        Example:
            ```python
            status = repo.status()
            if not status.is_clean:
                print("Working tree has changes:")
                for change in status.staged:
                    print(f"  Staged: {change}")
                for change in status.unstaged:
                    print(f"  Unstaged: {change}")
            ```
        """
        staged = []
        unstaged = []
        untracked = list(self._repo.untracked_files)

        # Get staged changes (index vs HEAD)
        if self._repo.head.is_valid():
            for diff in self._repo.index.diff(self._repo.head.commit):
                staged.append(self._diff_to_file_change(diff, staged=True))

        # Get unstaged changes (working tree vs index)
        for diff in self._repo.index.diff(None):
            unstaged.append(self._diff_to_file_change(diff, staged=False))

        # Get branch info
        branch = None
        is_detached = self._repo.head.is_detached

        if not is_detached:
            branch = self._repo.active_branch.name

        # Get commit SHA
        commit = None
        if self._repo.head.is_valid():
            commit = self._repo.head.commit.hexsha

        # Get ahead/behind counts
        ahead, behind = 0, 0
        if branch and not is_detached:
            try:
                tracking = self._repo.active_branch.tracking_branch()
                if tracking:
                    ahead = len(list(self._repo.iter_commits(f"{tracking}..HEAD")))
                    behind = len(list(self._repo.iter_commits(f"HEAD..{tracking}")))
            except Exception:
                pass

        return RepoStatus(
            branch=branch,
            commit=commit,
            is_detached=is_detached,
            is_clean=not staged and not unstaged and not untracked,
            staged=staged,
            unstaged=unstaged,
            untracked=untracked,
            ahead=ahead,
            behind=behind,
        )

    def _diff_to_file_change(self, diff, staged: bool) -> FileChange:
        """Convert a git diff to FileChange model."""
        status_map = {
            "A": FileStatus.ADDED,
            "D": FileStatus.DELETED,
            "M": FileStatus.MODIFIED,
            "R": FileStatus.RENAMED,
            "C": FileStatus.COPIED,
        }

        change_type = diff.change_type
        status = status_map.get(change_type, FileStatus.MODIFIED)

        path = diff.b_path or diff.a_path
        old_path = diff.a_path if change_type in ("R", "C") else None

        return FileChange(
            path=path,
            status=status,
            staged=staged,
            old_path=old_path,
        )

    @property
    def current_branch(self) -> Optional[str]:
        """Get the current branch name, or None if HEAD is detached."""
        if self._repo.head.is_detached:
            return None
        return self._repo.active_branch.name

    @property
    def current_commit(self) -> Optional[str]:
        """Get the current commit SHA."""
        if self._repo.head.is_valid():
            return self._repo.head.commit.hexsha
        return None

    @property
    def is_dirty(self) -> bool:
        """Check if the working tree has uncommitted changes."""
        return self._repo.is_dirty(untracked_files=True)

    # =========================================================================
    # Staging (Add/Remove)
    # =========================================================================

    def add(self, paths: Union[str, list[str]] = ".") -> None:
        """
        Stage files for commit.

        Args:
            paths: File path(s) to stage, or "." for all

        Raises:
            GitError: If staging fails
        """
        if isinstance(paths, str):
            paths = [paths]

        try:
            self._repo.index.add(paths)
        except GitCommandError as e:
            raise GitError(
                f"Failed to stage files: {e.stderr}",
                command=f"git add {' '.join(paths)}",
                return_code=e.status,
                stderr=e.stderr,
                repo_path=str(self.path),
            )

    def add_all(self) -> None:
        """Stage all changes (including untracked files)."""
        self.add(".")

    def reset(self, paths: Optional[Union[str, list[str]]] = None, hard: bool = False) -> None:
        """
        Unstage files or reset to a commit.

        Args:
            paths: File path(s) to unstage (None for all staged)
            hard: If True and no paths, do a hard reset (discards changes)

        Raises:
            GitError: If reset fails
        """
        try:
            if paths:
                if isinstance(paths, str):
                    paths = [paths]
                self._repo.index.reset(paths=paths)
            elif hard:
                self._repo.head.reset(index=True, working_tree=True)
            else:
                self._repo.index.reset()
        except GitCommandError as e:
            raise GitError(
                f"Failed to reset: {e.stderr}",
                command="git reset",
                return_code=e.status,
                stderr=e.stderr,
                repo_path=str(self.path),
            )

    def restore(self, paths: Union[str, list[str]], staged: bool = False) -> None:
        """
        Restore files to their previous state.

        Args:
            paths: File path(s) to restore
            staged: If True, restore from HEAD; if False, restore from index

        Raises:
            GitError: If restore fails
        """
        if isinstance(paths, str):
            paths = [paths]

        try:
            if staged:
                # Unstage files
                self._repo.index.reset(paths=paths)
            else:
                # Restore working tree from index
                self._repo.index.checkout(paths=paths, force=True)
        except GitCommandError as e:
            raise GitError(
                f"Failed to restore files: {e.stderr}",
                command="git restore",
                return_code=e.status,
                stderr=e.stderr,
                repo_path=str(self.path),
            )

    # =========================================================================
    # Commits
    # =========================================================================

    def commit(
        self,
        message: str,
        *,
        author: Optional[Author] = None,
        allow_empty: bool = False,
    ) -> Commit:
        """
        Create a new commit.

        Args:
            message: Commit message
            author: Author info (uses git config if not provided)
            allow_empty: Allow creating a commit with no changes

        Returns:
            The created Commit

        Raises:
            CommitError: If commit fails
        """
        try:
            kwargs = {"message": message}

            if author:
                from git import Actor
                actor = Actor(author.name, author.email)
                kwargs["author"] = actor
                kwargs["committer"] = actor

            if allow_empty:
                kwargs["allow_empty"] = True

            commit = self._repo.index.commit(**kwargs)
            return self._git_commit_to_model(commit)

        except GitCommandError as e:
            raise CommitError(
                f"Failed to create commit: {e.stderr}",
                command="git commit",
                return_code=e.status,
                stderr=e.stderr,
                repo_path=str(self.path),
            )

    def log(
        self,
        ref: str = "HEAD",
        *,
        limit: Optional[int] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        author: Optional[str] = None,
        path: Optional[str] = None,
    ) -> Iterator[Commit]:
        """
        Get commit history.

        Args:
            ref: Starting reference (branch, tag, or commit)
            limit: Maximum number of commits to return
            since: Only commits after this date
            until: Only commits before this date
            author: Filter by author name or email
            path: Only commits affecting this path

        Yields:
            Commit objects

        Example:
            ```python
            # Get last 10 commits
            for commit in repo.log(limit=10):
                print(f"{commit.short_sha}: {commit.subject}")

            # Get commits for a specific file
            for commit in repo.log(path="src/main.py"):
                print(commit.subject)
            ```
        """
        kwargs = {}
        if limit:
            kwargs["max_count"] = limit
        if since:
            kwargs["since"] = since
        if until:
            kwargs["until"] = until
        if author:
            kwargs["author"] = author

        try:
            if path:
                commits = self._repo.iter_commits(ref, paths=path, **kwargs)
            else:
                commits = self._repo.iter_commits(ref, **kwargs)

            for commit in commits:
                yield self._git_commit_to_model(commit)

        except GitCommandError as e:
            raise InvalidRefError(
                f"Invalid reference '{ref}': {e.stderr}",
                command=f"git log {ref}",
                return_code=e.status,
                stderr=e.stderr,
                repo_path=str(self.path),
            )

    def get_commit(self, ref: str = "HEAD") -> Commit:
        """
        Get a specific commit.

        Args:
            ref: Commit reference (SHA, branch, tag, HEAD, etc.)

        Returns:
            Commit object

        Raises:
            InvalidRefError: If the reference is invalid
        """
        try:
            commit = self._repo.commit(ref)
            return self._git_commit_to_model(commit)
        except Exception as e:
            raise InvalidRefError(
                f"Invalid reference '{ref}': {e}",
                repo_path=str(self.path),
            )

    def _git_commit_to_model(self, commit: GitCommit) -> Commit:
        """Convert GitPython commit to our model."""
        return Commit(
            sha=commit.hexsha,
            short_sha=commit.hexsha[:7],
            message=commit.message,
            author=Author(
                name=commit.author.name,
                email=commit.author.email,
            ),
            committer=Author(
                name=commit.committer.name,
                email=commit.committer.email,
            ),
            authored_date=datetime.fromtimestamp(
                commit.authored_date, tz=timezone.utc
            ),
            committed_date=datetime.fromtimestamp(
                commit.committed_date, tz=timezone.utc
            ),
            parent_shas=[p.hexsha for p in commit.parents],
        )

    # =========================================================================
    # Diff
    # =========================================================================

    def diff(
        self,
        ref1: Optional[str] = None,
        ref2: Optional[str] = None,
        *,
        staged: bool = False,
        path: Optional[str] = None,
    ) -> Diff:
        """
        Get differences between commits, index, or working tree.

        Args:
            ref1: First reference (default: index or HEAD)
            ref2: Second reference (default: working tree)
            staged: If True and no refs, show staged changes (index vs HEAD)
            path: Only show changes for this path

        Returns:
            Diff object with file changes

        Examples:
            ```python
            # Unstaged changes (working tree vs index)
            diff = repo.diff()

            # Staged changes (index vs HEAD)
            diff = repo.diff(staged=True)

            # Between two commits
            diff = repo.diff("main", "feature")

            # Changes in a specific file
            diff = repo.diff(path="src/main.py")
            ```
        """
        try:
            if ref1 and ref2:
                # Diff between two commits
                commit1 = self._repo.commit(ref1)
                commit2 = self._repo.commit(ref2)
                diffs = commit1.diff(commit2, paths=path)
            elif staged:
                # Staged changes (index vs HEAD)
                if self._repo.head.is_valid():
                    diffs = self._repo.head.commit.diff(paths=path)
                else:
                    diffs = []
            else:
                # Unstaged changes (working tree vs index)
                diffs = self._repo.index.diff(None, paths=path)

            files = []
            for d in diffs:
                file_diff = self._parse_diff(d)
                if file_diff:
                    files.append(file_diff)

            return Diff(files=files)

        except GitCommandError as e:
            raise DiffError(
                f"Failed to get diff: {e.stderr}",
                command="git diff",
                return_code=e.status,
                stderr=e.stderr,
                repo_path=str(self.path),
            )

    def _parse_diff(self, d) -> Optional[FileDiff]:
        """Parse a GitPython diff into our model."""
        status_map = {
            "A": FileStatus.ADDED,
            "D": FileStatus.DELETED,
            "M": FileStatus.MODIFIED,
            "R": FileStatus.RENAMED,
            "C": FileStatus.COPIED,
        }

        status = status_map.get(d.change_type, FileStatus.MODIFIED)
        path = d.b_path or d.a_path
        old_path = d.a_path if d.change_type in ("R", "C") else None

        # Get diff content
        hunks = []
        additions = 0
        deletions = 0

        try:
            diff_text = d.diff
            if diff_text:
                if isinstance(diff_text, bytes):
                    diff_text = diff_text.decode("utf-8", errors="replace")

                # Parse hunks from diff
                hunk_pattern = r"@@ -(\d+),?(\d*) \+(\d+),?(\d*) @@"
                parts = re.split(hunk_pattern, diff_text)

                i = 1
                while i < len(parts):
                    if i + 4 < len(parts):
                        old_start = int(parts[i])
                        old_count = int(parts[i + 1]) if parts[i + 1] else 1
                        new_start = int(parts[i + 2])
                        new_count = int(parts[i + 3]) if parts[i + 3] else 1
                        content = parts[i + 4] if i + 4 < len(parts) else ""

                        # Count additions and deletions
                        for line in content.split("\n"):
                            if line.startswith("+") and not line.startswith("+++"):
                                additions += 1
                            elif line.startswith("-") and not line.startswith("---"):
                                deletions += 1

                        hunks.append(
                            DiffHunk(
                                old_start=old_start,
                                old_count=old_count,
                                new_start=new_start,
                                new_count=new_count,
                                content=content,
                            )
                        )
                    i += 5

        except Exception:
            pass

        return FileDiff(
            path=path,
            old_path=old_path,
            status=status,
            hunks=hunks,
            is_binary=d.b_blob is None and d.a_blob is not None and d.change_type != "D",
            additions=additions,
            deletions=deletions,
        )

    def show(self, ref: str = "HEAD", path: Optional[str] = None) -> str:
        """
        Show the content of a file at a specific commit.

        Args:
            ref: Commit reference
            path: File path (if None, shows commit info)

        Returns:
            File content or commit info as string

        Raises:
            InvalidRefError: If reference is invalid
        """
        try:
            commit = self._repo.commit(ref)
            if path:
                blob = commit.tree / path
                return blob.data_stream.read().decode("utf-8", errors="replace")
            else:
                return f"{commit.hexsha}\n{commit.message}"
        except Exception as e:
            raise InvalidRefError(
                f"Cannot show '{path or ref}': {e}",
                repo_path=str(self.path),
            )

    # =========================================================================
    # Branches
    # =========================================================================

    def branches(self, *, remote: bool = False, all: bool = False) -> list[Branch]:
        """
        List branches.

        Args:
            remote: Show only remote branches
            all: Show both local and remote branches

        Returns:
            List of Branch objects
        """
        result = []

        if not remote or all:
            # Local branches
            for branch in self._repo.branches:
                tracking = None
                ahead, behind = 0, 0

                try:
                    tb = branch.tracking_branch()
                    if tb:
                        tracking = tb.name
                        ahead = len(list(self._repo.iter_commits(f"{tb}..{branch}")))
                        behind = len(list(self._repo.iter_commits(f"{branch}..{tb}")))
                except Exception:
                    pass

                result.append(
                    Branch(
                        name=branch.name,
                        commit_sha=branch.commit.hexsha,
                        is_current=branch == self._repo.active_branch
                        if not self._repo.head.is_detached
                        else False,
                        is_remote=False,
                        tracking=tracking,
                        ahead=ahead,
                        behind=behind,
                    )
                )

        if remote or all:
            # Remote branches
            for ref in self._repo.remote().refs:
                if ref.name == "origin/HEAD":
                    continue
                result.append(
                    Branch(
                        name=ref.name,
                        commit_sha=ref.commit.hexsha,
                        is_current=False,
                        is_remote=True,
                    )
                )

        return result

    def create_branch(
        self,
        name: str,
        ref: str = "HEAD",
        *,
        checkout: bool = False,
    ) -> Branch:
        """
        Create a new branch.

        Args:
            name: Branch name
            ref: Starting point (commit, branch, tag)
            checkout: Switch to the new branch after creating

        Returns:
            The created Branch

        Raises:
            BranchError: If branch creation fails
        """
        try:
            commit = self._repo.commit(ref)
            branch = self._repo.create_head(name, commit)

            if checkout:
                branch.checkout()

            return Branch(
                name=branch.name,
                commit_sha=branch.commit.hexsha,
                is_current=checkout,
                is_remote=False,
            )

        except GitCommandError as e:
            raise BranchError(
                f"Failed to create branch '{name}': {e.stderr}",
                command=f"git branch {name}",
                return_code=e.status,
                stderr=e.stderr,
                repo_path=str(self.path),
            )

    def delete_branch(self, name: str, *, force: bool = False) -> None:
        """
        Delete a branch.

        Args:
            name: Branch name
            force: Force delete even if not merged

        Raises:
            BranchError: If deletion fails
        """
        try:
            self._repo.delete_head(name, force=force)
        except GitCommandError as e:
            raise BranchError(
                f"Failed to delete branch '{name}': {e.stderr}",
                command=f"git branch -d {name}",
                return_code=e.status,
                stderr=e.stderr,
                repo_path=str(self.path),
            )

    def checkout(
        self,
        ref: str,
        *,
        create: bool = False,
        force: bool = False,
    ) -> None:
        """
        Checkout a branch, tag, or commit.

        Args:
            ref: Reference to checkout
            create: Create branch if it doesn't exist
            force: Force checkout, discarding local changes

        Raises:
            CheckoutError: If checkout fails
        """
        try:
            if create:
                branch = self._repo.create_head(ref)
                branch.checkout(force=force)
            else:
                self._repo.git.checkout(ref, force=force)

        except GitCommandError as e:
            raise CheckoutError(
                f"Failed to checkout '{ref}': {e.stderr}",
                command=f"git checkout {ref}",
                return_code=e.status,
                stderr=e.stderr,
                repo_path=str(self.path),
            )

    # =========================================================================
    # Remotes
    # =========================================================================

    def remotes(self) -> list[Remote]:
        """
        List configured remotes.

        Returns:
            List of Remote objects
        """
        result = []
        for remote in self._repo.remotes:
            urls = list(remote.urls)
            result.append(
                Remote(
                    name=remote.name,
                    url=urls[0] if urls else "",
                    fetch_url=urls[0] if urls else None,
                    push_url=urls[1] if len(urls) > 1 else None,
                )
            )
        return result

    def add_remote(self, name: str, url: str) -> Remote:
        """
        Add a new remote.

        Args:
            name: Remote name
            url: Remote URL

        Returns:
            The created Remote

        Raises:
            RemoteError: If adding fails
        """
        try:
            remote = self._repo.create_remote(name, url)
            return Remote(name=remote.name, url=url)
        except GitCommandError as e:
            raise RemoteError(
                f"Failed to add remote '{name}': {e.stderr}",
                command=f"git remote add {name} {url}",
                return_code=e.status,
                stderr=e.stderr,
                repo_path=str(self.path),
            )

    def fetch(
        self,
        remote: str = "origin",
        *,
        prune: bool = False,
        all_remotes: bool = False,
    ) -> None:
        """
        Fetch from remote(s).

        Args:
            remote: Remote name
            prune: Remove deleted remote branches
            all_remotes: Fetch from all remotes

        Raises:
            FetchError: If fetch fails
        """
        try:
            if all_remotes:
                for r in self._repo.remotes:
                    r.fetch(prune=prune)
            else:
                self._repo.remote(remote).fetch(prune=prune)
        except GitCommandError as e:
            raise FetchError(
                f"Failed to fetch from '{remote}': {e.stderr}",
                command=f"git fetch {remote}",
                return_code=e.status,
                stderr=e.stderr,
                repo_path=str(self.path),
            )

    def pull(
        self,
        remote: str = "origin",
        branch: Optional[str] = None,
        *,
        rebase: bool = False,
    ) -> None:
        """
        Pull changes from remote.

        Args:
            remote: Remote name
            branch: Branch to pull (default: current tracking branch)
            rebase: Rebase instead of merge

        Raises:
            PullError: If pull fails
        """
        try:
            r = self._repo.remote(remote)
            kwargs = {}
            if rebase:
                kwargs["rebase"] = True
            if branch:
                r.pull(branch, **kwargs)
            else:
                r.pull(**kwargs)
        except GitCommandError as e:
            raise PullError(
                f"Failed to pull from '{remote}': {e.stderr}",
                command=f"git pull {remote}",
                return_code=e.status,
                stderr=e.stderr,
                repo_path=str(self.path),
            )

    def push(
        self,
        remote: str = "origin",
        branch: Optional[str] = None,
        *,
        force: bool = False,
        set_upstream: bool = False,
        tags: bool = False,
    ) -> None:
        """
        Push changes to remote.

        Args:
            remote: Remote name
            branch: Branch to push (default: current branch)
            force: Force push
            set_upstream: Set upstream tracking
            tags: Push tags

        Raises:
            PushError: If push fails
        """
        try:
            r = self._repo.remote(remote)
            refspec = branch or self.current_branch

            kwargs = {}
            if force:
                kwargs["force"] = True
            if set_upstream:
                kwargs["set_upstream"] = True

            if tags:
                r.push(tags=True, **kwargs)
            if refspec:
                r.push(refspec, **kwargs)
            else:
                r.push(**kwargs)

        except GitCommandError as e:
            raise PushError(
                f"Failed to push to '{remote}': {e.stderr}",
                command=f"git push {remote}",
                return_code=e.status,
                stderr=e.stderr,
                repo_path=str(self.path),
            )

    # =========================================================================
    # Merging
    # =========================================================================

    def merge(
        self,
        ref: str,
        *,
        message: Optional[str] = None,
        no_commit: bool = False,
        squash: bool = False,
    ) -> Optional[Commit]:
        """
        Merge a branch or commit.

        Args:
            ref: Reference to merge
            message: Custom merge commit message
            no_commit: Merge but don't commit
            squash: Squash commits into a single commit

        Returns:
            Merge commit (if created) or None

        Raises:
            MergeError: If merge fails or has conflicts
        """
        try:
            args = [ref]
            if message:
                self._repo.git.merge(ref, m=message, no_commit=no_commit, squash=squash)
            else:
                self._repo.git.merge(ref, no_commit=no_commit, squash=squash)

            if not no_commit and not squash:
                return self.get_commit("HEAD")
            return None

        except GitCommandError as e:
            # Check for merge conflicts
            if "CONFLICT" in e.stderr or "Automatic merge failed" in e.stderr:
                # Get conflicting files
                conflicting = []
                status = self._repo.git.status(porcelain=True)
                for line in status.split("\n"):
                    if line.startswith("UU ") or line.startswith("AA "):
                        conflicting.append(line[3:])

                raise MergeError(
                    f"Merge conflict: {e.stderr}",
                    command=f"git merge {ref}",
                    return_code=e.status,
                    stderr=e.stderr,
                    repo_path=str(self.path),
                    conflicting_files=conflicting,
                )

            raise MergeError(
                f"Failed to merge '{ref}': {e.stderr}",
                command=f"git merge {ref}",
                return_code=e.status,
                stderr=e.stderr,
                repo_path=str(self.path),
            )

    def abort_merge(self) -> None:
        """Abort an in-progress merge."""
        try:
            self._repo.git.merge(abort=True)
        except GitCommandError as e:
            raise MergeError(
                f"Failed to abort merge: {e.stderr}",
                command="git merge --abort",
                return_code=e.status,
                stderr=e.stderr,
                repo_path=str(self.path),
            )

    # =========================================================================
    # Tags
    # =========================================================================

    def tags(self) -> list[Tag]:
        """
        List all tags.

        Returns:
            List of Tag objects
        """
        result = []
        for tag in self._repo.tags:
            tag_obj = tag.tag  # Annotated tag object, or None
            result.append(
                Tag(
                    name=tag.name,
                    commit_sha=tag.commit.hexsha,
                    message=tag_obj.message if tag_obj else None,
                    tagger=Author(name=tag_obj.tagger.name, email=tag_obj.tagger.email)
                    if tag_obj and tag_obj.tagger
                    else None,
                    is_annotated=tag_obj is not None,
                )
            )
        return result

    def create_tag(
        self,
        name: str,
        ref: str = "HEAD",
        *,
        message: Optional[str] = None,
    ) -> Tag:
        """
        Create a new tag.

        Args:
            name: Tag name
            ref: Reference to tag
            message: Tag message (creates annotated tag)

        Returns:
            The created Tag
        """
        try:
            commit = self._repo.commit(ref)
            if message:
                tag = self._repo.create_tag(name, commit, message=message)
            else:
                tag = self._repo.create_tag(name, commit)

            return Tag(
                name=tag.name,
                commit_sha=commit.hexsha,
                message=message,
                is_annotated=message is not None,
            )
        except GitCommandError as e:
            raise GitError(
                f"Failed to create tag '{name}': {e.stderr}",
                command=f"git tag {name}",
                return_code=e.status,
                stderr=e.stderr,
                repo_path=str(self.path),
            )

    # =========================================================================
    # File Operations
    # =========================================================================

    def read_file(self, path: str, ref: str = "HEAD") -> str:
        """
        Read file content at a specific commit.

        Args:
            path: File path relative to repo root
            ref: Commit reference

        Returns:
            File content as string

        Raises:
            GitError: If file doesn't exist
        """
        return self.show(ref, path)

    def list_files(self, ref: str = "HEAD", path: str = "") -> list[str]:
        """
        List files in the repository at a specific commit.

        Args:
            ref: Commit reference
            path: Subdirectory path (empty for root)

        Returns:
            List of file paths
        """
        try:
            commit = self._repo.commit(ref)
            tree = commit.tree

            if path:
                tree = tree / path

            files = []
            for item in tree.traverse():
                if item.type == "blob":
                    files.append(item.path)
            return files

        except Exception as e:
            raise GitError(
                f"Failed to list files: {e}",
                repo_path=str(self.path),
            )

    # =========================================================================
    # Utility
    # =========================================================================

    def __repr__(self) -> str:
        branch = self.current_branch or "detached"
        return f"GitRepository(path={self.path!r}, branch={branch!r})"

    def __str__(self) -> str:
        return str(self.path)
