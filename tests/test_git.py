"""Tests for Git interface."""

import os
import tempfile
from pathlib import Path

import pytest

from computor_agent.git import (
    GitRepository,
    GitError,
    RepositoryNotFoundError,
    FileStatus,
)


class TestGitRepository:
    """Tests for GitRepository class."""

    @pytest.fixture
    def temp_repo(self):
        """Create a temporary Git repository for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = GitRepository.init(tmpdir, initial_branch="main")
            # Create initial commit
            readme = Path(tmpdir) / "README.md"
            readme.write_text("# Test Repository\n")
            repo.add("README.md")
            repo.commit("Initial commit")
            yield repo

    def test_init_repository(self):
        """Test initializing a new repository."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = GitRepository.init(tmpdir)
            assert repo.path == Path(tmpdir).resolve()
            assert (Path(tmpdir) / ".git").exists()

    def test_init_with_initial_branch(self):
        """Test initializing with a custom branch name."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = GitRepository.init(tmpdir, initial_branch="main")
            # Create a file and commit to establish the branch
            readme = Path(tmpdir) / "README.md"
            readme.write_text("# Test\n")
            repo.add("README.md")
            repo.commit("Initial commit")
            assert repo.current_branch == "main"

    def test_open_nonexistent_repo(self):
        """Test opening a non-existent path."""
        with pytest.raises(RepositoryNotFoundError):
            GitRepository("/nonexistent/path")

    def test_open_non_repo_directory(self):
        """Test opening a directory that's not a repo."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(RepositoryNotFoundError):
                GitRepository(tmpdir)

    def test_status_clean(self, temp_repo):
        """Test status on a clean repository."""
        status = temp_repo.status()
        assert status.is_clean
        assert status.branch == "main"
        assert len(status.staged) == 0
        assert len(status.unstaged) == 0
        assert len(status.untracked) == 0

    def test_status_with_changes(self, temp_repo):
        """Test status with various changes."""
        # Add an untracked file
        new_file = temp_repo.path / "new_file.txt"
        new_file.write_text("new content")

        status = temp_repo.status()
        assert not status.is_clean
        assert "new_file.txt" in status.untracked

    def test_status_staged_changes(self, temp_repo):
        """Test status with staged changes."""
        # Create and stage a new file
        new_file = temp_repo.path / "staged.txt"
        new_file.write_text("staged content")
        temp_repo.add("staged.txt")

        status = temp_repo.status()
        assert len(status.staged) == 1
        assert status.staged[0].path == "staged.txt"
        assert status.staged[0].status == FileStatus.ADDED

    def test_add_and_commit(self, temp_repo):
        """Test staging and committing files."""
        # Create a new file
        new_file = temp_repo.path / "test.txt"
        new_file.write_text("test content")

        # Stage and commit
        temp_repo.add("test.txt")
        commit = temp_repo.commit("Add test file")

        assert commit.subject == "Add test file"
        assert temp_repo.status().is_clean

    def test_add_all(self, temp_repo):
        """Test staging all changes."""
        # Create multiple files
        (temp_repo.path / "file1.txt").write_text("content1")
        (temp_repo.path / "file2.txt").write_text("content2")

        temp_repo.add_all()
        status = temp_repo.status()

        assert len(status.staged) == 2

    def test_log(self, temp_repo):
        """Test commit log."""
        # Create a few commits
        for i in range(3):
            file = temp_repo.path / f"file{i}.txt"
            file.write_text(f"content {i}")
            temp_repo.add(f"file{i}.txt")
            temp_repo.commit(f"Commit {i}")

        commits = list(temp_repo.log(limit=5))
        assert len(commits) == 4  # 3 new + 1 initial
        assert commits[0].subject == "Commit 2"
        assert commits[3].subject == "Initial commit"

    def test_get_commit(self, temp_repo):
        """Test getting a specific commit."""
        commit = temp_repo.get_commit("HEAD")
        assert commit.subject == "Initial commit"
        assert len(commit.sha) == 40
        assert len(commit.short_sha) == 7

    def test_diff_unstaged(self, temp_repo):
        """Test diff for unstaged changes."""
        # Modify a file
        readme = temp_repo.path / "README.md"
        readme.write_text("# Modified Repository\n")

        diff = temp_repo.diff()
        assert len(diff.files) == 1
        assert diff.files[0].path == "README.md"
        assert diff.files[0].status == FileStatus.MODIFIED

    def test_diff_staged(self, temp_repo):
        """Test diff for staged changes."""
        # Create and stage a file
        new_file = temp_repo.path / "new.txt"
        new_file.write_text("new content")
        temp_repo.add("new.txt")

        diff = temp_repo.diff(staged=True)
        assert len(diff.files) == 1
        assert diff.files[0].path == "new.txt"

    def test_branches(self, temp_repo):
        """Test listing branches."""
        branches = temp_repo.branches()
        assert len(branches) == 1
        assert branches[0].name == "main"
        assert branches[0].is_current

    def test_create_branch(self, temp_repo):
        """Test creating a new branch."""
        branch = temp_repo.create_branch("feature")
        assert branch.name == "feature"

        branches = temp_repo.branches()
        assert len(branches) == 2

    def test_create_and_checkout_branch(self, temp_repo):
        """Test creating and checking out a branch."""
        temp_repo.create_branch("feature", checkout=True)
        assert temp_repo.current_branch == "feature"

    def test_checkout_branch(self, temp_repo):
        """Test checking out a branch."""
        temp_repo.create_branch("feature")
        temp_repo.checkout("feature")
        assert temp_repo.current_branch == "feature"

    def test_delete_branch(self, temp_repo):
        """Test deleting a branch."""
        temp_repo.create_branch("to-delete")
        temp_repo.delete_branch("to-delete")

        branches = temp_repo.branches()
        assert len(branches) == 1

    def test_is_dirty(self, temp_repo):
        """Test is_dirty property."""
        assert not temp_repo.is_dirty

        new_file = temp_repo.path / "dirty.txt"
        new_file.write_text("dirty")

        assert temp_repo.is_dirty

    def test_current_branch(self, temp_repo):
        """Test current_branch property."""
        assert temp_repo.current_branch == "main"

    def test_current_commit(self, temp_repo):
        """Test current_commit property."""
        sha = temp_repo.current_commit
        assert sha is not None
        assert len(sha) == 40

    def test_read_file(self, temp_repo):
        """Test reading file at a commit."""
        content = temp_repo.read_file("README.md")
        assert content == "# Test Repository\n"

    def test_list_files(self, temp_repo):
        """Test listing files in repository."""
        files = temp_repo.list_files()
        assert "README.md" in files

    def test_reset_staged(self, temp_repo):
        """Test unstaging files."""
        new_file = temp_repo.path / "staged.txt"
        new_file.write_text("content")
        temp_repo.add("staged.txt")

        assert len(temp_repo.status().staged) == 1

        temp_repo.reset(["staged.txt"])
        assert len(temp_repo.status().staged) == 0

    def test_tags(self, temp_repo):
        """Test listing tags."""
        tags = temp_repo.tags()
        assert len(tags) == 0

    def test_create_tag(self, temp_repo):
        """Test creating a tag."""
        tag = temp_repo.create_tag("v1.0.0")
        assert tag.name == "v1.0.0"

        tags = temp_repo.tags()
        assert len(tags) == 1

    def test_create_annotated_tag(self, temp_repo):
        """Test creating an annotated tag."""
        tag = temp_repo.create_tag("v1.0.0", message="Release 1.0.0")
        assert tag.name == "v1.0.0"
        assert tag.message == "Release 1.0.0"
        assert tag.is_annotated

    def test_remotes_empty(self, temp_repo):
        """Test listing remotes on repo without remotes."""
        remotes = temp_repo.remotes()
        assert len(remotes) == 0


class TestGitRepositoryClone:
    """Tests for cloning repositories."""

    def test_clone_invalid_url(self):
        """Test cloning from invalid URL."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(GitError):
                GitRepository.clone("https://invalid-url-that-does-not-exist.git", tmpdir)


class TestCommitModel:
    """Tests for Commit model."""

    @pytest.fixture
    def temp_repo(self):
        """Create a temporary Git repository for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = GitRepository.init(tmpdir, initial_branch="main")
            readme = Path(tmpdir) / "README.md"
            readme.write_text("# Test\n")
            repo.add("README.md")
            repo.commit("Subject line\n\nBody paragraph.")
            yield repo

    def test_commit_subject(self, temp_repo):
        """Test commit subject extraction."""
        commit = temp_repo.get_commit("HEAD")
        assert commit.subject == "Subject line"

    def test_commit_body(self, temp_repo):
        """Test commit body extraction."""
        commit = temp_repo.get_commit("HEAD")
        assert commit.body == "Body paragraph."

    def test_commit_is_not_merge(self, temp_repo):
        """Test is_merge for regular commit."""
        commit = temp_repo.get_commit("HEAD")
        assert not commit.is_merge


class TestFileChange:
    """Tests for FileChange model."""

    def test_file_change_str(self):
        """Test string representation."""
        from computor_agent.git import FileChange, FileStatus

        change = FileChange(path="test.py", status=FileStatus.MODIFIED, staged=True)
        assert "staged" in str(change)
        assert "modified" in str(change)
        assert "test.py" in str(change)

    def test_file_change_rename_str(self):
        """Test string representation for rename."""
        from computor_agent.git import FileChange, FileStatus

        change = FileChange(
            path="new.py",
            status=FileStatus.RENAMED,
            staged=True,
            old_path="old.py",
        )
        assert "old.py" in str(change)
        assert "new.py" in str(change)


class TestRepoStatus:
    """Tests for RepoStatus model."""

    def test_has_changes(self):
        """Test has_changes property."""
        from computor_agent.git import RepoStatus, FileChange, FileStatus

        # Clean status
        status = RepoStatus(branch="main", is_clean=True)
        assert not status.has_changes

        # With staged
        status = RepoStatus(
            branch="main",
            staged=[FileChange(path="a.py", status=FileStatus.ADDED, staged=True)],
        )
        assert status.has_changes

        # With untracked
        status = RepoStatus(branch="main", untracked=["new.txt"])
        assert status.has_changes
