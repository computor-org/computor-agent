"""Tests for services module."""

import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from computor_agent.services import (
    RepositoryService,
    RepositoryType,
    WorkspaceDirectories,
    SyncResult,
    RepositoryInfo,
    slugify,
    derive_repository_name,
)
from computor_agent.settings.credentials import GitCredentialsStore
from computor_agent.git import GitCredentials


class TestSlugify:
    """Tests for slugify function."""

    def test_slugify_simple(self):
        """Test basic slugification."""
        assert slugify("hello-world") == "hello-world"

    def test_slugify_removes_git_suffix(self):
        """Test .git suffix removal."""
        assert slugify("my-repo.git") == "my-repo"

    def test_slugify_replaces_special_chars(self):
        """Test special character replacement."""
        assert slugify("Hello World!") == "hello-world"

    def test_slugify_strips_hyphens(self):
        """Test leading/trailing hyphen removal."""
        assert slugify("--hello--") == "hello"

    def test_slugify_lowercase(self):
        """Test lowercase conversion."""
        assert slugify("MyRepo") == "myrepo"

    def test_slugify_none(self):
        """Test None input."""
        assert slugify(None) is None

    def test_slugify_empty(self):
        """Test empty string."""
        assert slugify("") is None

    def test_slugify_preserves_underscores(self):
        """Test that underscores are preserved."""
        assert slugify("my_repo") == "my_repo"


class TestDeriveRepositoryName:
    """Tests for derive_repository_name function."""

    def test_prefers_full_path(self):
        """Test full_path is preferred and slashes become dots."""
        name = derive_repository_name(
            full_path="course/student-123",
            submission_group_id="uuid-456",
        )
        assert name == "course.student-123"

    def test_fallback_to_submission_group_id(self):
        """Test fallback to submission_group_id."""
        name = derive_repository_name(submission_group_id="uuid-123")
        assert name == "uuid-123"

    def test_fallback_to_member_id(self):
        """Test fallback to member_id."""
        name = derive_repository_name(member_id="member-456")
        assert name == "member-456"

    def test_fallback_to_course_id(self):
        """Test fallback to course_id."""
        name = derive_repository_name(course_id="course-789")
        assert name == "course-789"

    def test_fallback_to_url(self):
        """Test fallback to URL extraction."""
        name = derive_repository_name(
            remote_url="https://gitlab.example.com/group/my-repo.git"
        )
        assert name == "my-repo"

    def test_default_repository(self):
        """Test default return value."""
        name = derive_repository_name()
        assert name == "repository"


class TestSyncResult:
    """Tests for SyncResult dataclass."""

    def test_create_sync_result(self):
        """Test creating a SyncResult."""
        result = SyncResult(
            path=Path("/tmp/test"),
            url="https://example.com/repo.git",
            action="cloned",
        )
        assert result.path == Path("/tmp/test")
        assert result.url == "https://example.com/repo.git"
        assert result.action == "cloned"
        assert result.error is None
        assert result.submission_group_id is None
        assert result.commit_sha is None

    def test_sync_result_with_all_fields(self):
        """Test SyncResult with all fields populated."""
        result = SyncResult(
            path=Path("/tmp/test"),
            url="https://example.com/repo.git",
            action="failed",
            error="Connection refused",
            submission_group_id="group-123",
            commit_sha="abc123def456",
        )
        assert result.error == "Connection refused"
        assert result.submission_group_id == "group-123"
        assert result.commit_sha == "abc123def456"


class TestRepositoryInfo:
    """Tests for RepositoryInfo dataclass."""

    def test_create_repository_info(self):
        """Test creating a RepositoryInfo."""
        info = RepositoryInfo(
            path=Path("/tmp/repo"),
            url="https://gitlab.example.com/group/repo.git",
            repo_type=RepositoryType.STUDENT,
            name="my-repo",
        )
        assert info.path == Path("/tmp/repo")
        assert info.url == "https://gitlab.example.com/group/repo.git"
        assert info.repo_type == RepositoryType.STUDENT
        assert info.name == "my-repo"
        assert info.member_names == []

    def test_repository_info_with_all_fields(self):
        """Test RepositoryInfo with all fields."""
        info = RepositoryInfo(
            path=Path("/tmp/repo"),
            url="https://gitlab.example.com/group/repo.git",
            repo_type=RepositoryType.REVIEW,
            name="my-repo",
            submission_group_id="sg-123",
            course_id="course-456",
            member_names=["Alice Smith", "Bob Jones"],
        )
        assert info.submission_group_id == "sg-123"
        assert info.course_id == "course-456"
        assert info.member_names == ["Alice Smith", "Bob Jones"]


class TestWorkspaceDirectories:
    """Tests for WorkspaceDirectories dataclass."""

    def test_workspace_directories(self):
        """Test workspace directories structure."""
        root = Path("/workspace")
        dirs = WorkspaceDirectories(
            root=root,
            student=root / "student",
            review=root / "review",
            review_repositories=root / "review" / "repositories",
            review_reference=root / "review" / "reference",
            review_submissions=root / "review" / "submissions",
            reference=root / "reference",
        )
        assert dirs.root == Path("/workspace")
        assert dirs.student == Path("/workspace/student")
        assert dirs.review_repositories == Path("/workspace/review/repositories")


class TestRepositoryService:
    """Tests for RepositoryService."""

    def test_init_with_defaults(self):
        """Test RepositoryService initialization with defaults."""
        mock_client = MagicMock()
        service = RepositoryService(client=mock_client)

        assert service._client is mock_client
        assert service.workspace_root == Path.cwd()
        assert len(service._credentials_store) == 0

    def test_init_with_credentials_store(self):
        """Test RepositoryService with credentials store."""
        mock_client = MagicMock()
        creds = GitCredentialsStore()
        creds.add("https://gitlab.example.com", "test-token")

        service = RepositoryService(
            client=mock_client,
            credentials_store=creds,
        )

        assert len(service._credentials_store) == 1

    def test_init_with_workspace_root(self):
        """Test RepositoryService with custom workspace root."""
        mock_client = MagicMock()
        workspace = Path("/tmp/custom-workspace")

        service = RepositoryService(
            client=mock_client,
            workspace_root=workspace,
        )

        assert service.workspace_root == workspace

    def test_workspace_root_setter(self):
        """Test setting workspace root."""
        mock_client = MagicMock()
        service = RepositoryService(client=mock_client)

        new_path = Path("/new/workspace")
        service.workspace_root = new_path

        assert service.workspace_root == new_path

    def test_get_directories(self):
        """Test getting workspace directories."""
        mock_client = MagicMock()
        service = RepositoryService(
            client=mock_client,
            workspace_root=Path("/workspace"),
        )

        dirs = service.get_directories()

        assert dirs.root == Path("/workspace")
        assert dirs.student == Path("/workspace/student")
        assert dirs.review == Path("/workspace/review")
        assert dirs.review_repositories == Path("/workspace/review/repositories")
        assert dirs.review_reference == Path("/workspace/review/reference")
        assert dirs.review_submissions == Path("/workspace/review/submissions")
        assert dirs.reference == Path("/workspace/reference")

    def test_get_student_repo_path(self):
        """Test getting student repo path."""
        mock_client = MagicMock()
        service = RepositoryService(
            client=mock_client,
            workspace_root=Path("/workspace"),
        )

        path = service.get_student_repo_path("my-repo")
        assert path == Path("/workspace/student/my-repo")

    def test_get_review_repo_path(self):
        """Test getting review repo path."""
        mock_client = MagicMock()
        service = RepositoryService(
            client=mock_client,
            workspace_root=Path("/workspace"),
        )

        path = service.get_review_repo_path("student-repo")
        assert path == Path("/workspace/review/repositories/student-repo")

    def test_get_review_reference_path(self):
        """Test getting review reference path."""
        mock_client = MagicMock()
        service = RepositoryService(
            client=mock_client,
            workspace_root=Path("/workspace"),
        )

        path = service.get_review_reference_path("example-v1")
        assert path == Path("/workspace/review/reference/example-v1")

    def test_get_review_submission_path(self):
        """Test getting review submission path."""
        mock_client = MagicMock()
        service = RepositoryService(
            client=mock_client,
            workspace_root=Path("/workspace"),
        )

        path = service.get_review_submission_path("sg-123", "artifact-456")
        assert path == Path("/workspace/review/submissions/sg-123/artifact-456")

    def test_get_reference_repo_path(self):
        """Test getting reference repo path."""
        mock_client = MagicMock()
        service = RepositoryService(
            client=mock_client,
            workspace_root=Path("/workspace"),
        )

        path = service.get_reference_repo_path("course-123")
        assert path == Path("/workspace/reference/course-123")

    def test_get_credentials_for_url(self):
        """Test getting credentials for a URL."""
        mock_client = MagicMock()
        creds = GitCredentialsStore()
        creds.add("https://gitlab.example.com", "my-token")

        service = RepositoryService(
            client=mock_client,
            credentials_store=creds,
        )

        # Should find credentials
        result = service._get_credentials_for_url(
            "https://gitlab.example.com/group/repo.git"
        )
        assert result is not None
        assert isinstance(result, GitCredentials)

        # Should not find credentials for different host
        result = service._get_credentials_for_url(
            "https://github.com/user/repo.git"
        )
        assert result is None

    def test_extract_repository_info_from_properties(self):
        """Test extracting repository info from submission group properties."""
        mock_client = MagicMock()
        service = RepositoryService(client=mock_client)

        mock_group = MagicMock()
        mock_group.properties = {
            "repository_url": "https://gitlab.example.com/group/repo.git"
        }

        url, full_path = service._extract_repository_info(mock_group)
        assert url == "https://gitlab.example.com/group/repo.git"
        assert full_path is None

    def test_extract_repository_info_nested(self):
        """Test extracting repository info from nested properties."""
        mock_client = MagicMock()
        service = RepositoryService(client=mock_client)

        mock_group = MagicMock()
        mock_group.properties = {
            "repository": {
                "clone_url": "https://gitlab.example.com/group/repo.git",
                "full_path": "group/repo",
            }
        }

        url, full_path = service._extract_repository_info(mock_group)
        assert url == "https://gitlab.example.com/group/repo.git"
        assert full_path == "group/repo"

    def test_extract_repository_info_no_properties(self):
        """Test extracting repository info when properties is None."""
        mock_client = MagicMock()
        service = RepositoryService(client=mock_client)

        mock_group = MagicMock()
        mock_group.properties = None

        url, full_path = service._extract_repository_info(mock_group)
        assert url is None
        assert full_path is None

    def test_list_student_repositories(self, tmp_path):
        """Test listing student repositories."""
        mock_client = MagicMock()
        service = RepositoryService(
            client=mock_client,
            workspace_root=tmp_path,
        )

        # Create fake repository structure
        student_dir = tmp_path / "student"
        student_dir.mkdir()

        repo1 = student_dir / "repo1"
        repo1.mkdir()
        (repo1 / ".git").mkdir()

        repo2 = student_dir / "repo2"
        repo2.mkdir()
        (repo2 / ".git").mkdir()

        # Non-repo directory (should be excluded)
        not_repo = student_dir / "not-a-repo"
        not_repo.mkdir()

        repos = service.list_student_repositories()
        assert len(repos) == 2
        assert repo1 in repos
        assert repo2 in repos
        assert not_repo not in repos

    def test_list_review_repositories(self, tmp_path):
        """Test listing review repositories."""
        mock_client = MagicMock()
        service = RepositoryService(
            client=mock_client,
            workspace_root=tmp_path,
        )

        # Create fake repository structure
        review_repos = tmp_path / "review" / "repositories"
        review_repos.mkdir(parents=True)

        repo1 = review_repos / "student-a"
        repo1.mkdir()
        (repo1 / ".git").mkdir()

        repos = service.list_review_repositories()
        assert len(repos) == 1
        assert repo1 in repos

    def test_repository_exists(self, tmp_path):
        """Test checking if repository exists."""
        mock_client = MagicMock()
        service = RepositoryService(
            client=mock_client,
            workspace_root=tmp_path,
        )

        # Create a repo
        repo_path = tmp_path / "test-repo"
        repo_path.mkdir()
        (repo_path / ".git").mkdir()

        assert service.repository_exists(repo_path) is True
        assert service.repository_exists(tmp_path / "nonexistent") is False


class TestRepositoryServiceAsync:
    """Async tests for RepositoryService."""

    @pytest.mark.asyncio
    async def test_ensure_directories(self, tmp_path):
        """Test creating workspace directories."""
        mock_client = MagicMock()
        service = RepositoryService(
            client=mock_client,
            workspace_root=tmp_path,
        )

        await service.ensure_directories()

        assert (tmp_path / "student").exists()
        assert (tmp_path / "review").exists()
        assert (tmp_path / "review" / "repositories").exists()
        assert (tmp_path / "review" / "reference").exists()
        assert (tmp_path / "review" / "submissions").exists()
        assert (tmp_path / "reference").exists()

    @pytest.mark.asyncio
    async def test_backend_url_marker(self, tmp_path):
        """Test reading/writing backend URL marker."""
        mock_client = MagicMock()
        service = RepositoryService(
            client=mock_client,
            workspace_root=tmp_path,
        )

        # Initially no marker
        url = await service.get_backend_url()
        assert url is None

        # Set backend URL
        await service.set_backend_url("https://api.example.com")

        # Read it back
        url = await service.get_backend_url()
        assert url == "https://api.example.com"

        # Verify file contents
        marker_path = tmp_path / ".computor"
        assert marker_path.exists()
        data = json.loads(marker_path.read_text())
        assert data["backendUrl"] == "https://api.example.com"

    @pytest.mark.asyncio
    async def test_get_submission_groups(self):
        """Test getting submission groups from API."""
        mock_client = MagicMock()
        mock_client.tutors = MagicMock()
        mock_client.tutors.get_submission_groups = AsyncMock(return_value=[])

        service = RepositoryService(client=mock_client)

        result = await service.get_submission_groups(course_content_id="content-123")

        mock_client.tutors.get_submission_groups.assert_called_once_with(
            course_content_id="content-123"
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_get_submission_group(self):
        """Test getting a single submission group."""
        mock_client = MagicMock()
        mock_client.tutors = MagicMock()

        mock_group = MagicMock()
        mock_group.id = "group-123"
        mock_client.tutors.submission_groups = AsyncMock(return_value=mock_group)

        service = RepositoryService(client=mock_client)

        result = await service.get_submission_group("group-123")

        mock_client.tutors.submission_groups.assert_called_once_with("group-123")
        assert result.id == "group-123"

    @pytest.mark.asyncio
    async def test_sync_repository_clone(self, tmp_path):
        """Test syncing a repository that doesn't exist (clone)."""
        mock_client = MagicMock()
        creds = GitCredentialsStore()

        service = RepositoryService(
            client=mock_client,
            credentials_store=creds,
            workspace_root=tmp_path,
        )

        repo_path = tmp_path / "new-repo"

        with patch.object(service, 'clone_repository') as mock_clone:
            mock_repo = MagicMock()
            mock_commit = MagicMock()
            mock_commit.sha = "abc123"
            mock_repo.head.return_value = mock_commit
            mock_clone.return_value = mock_repo

            result = await service.sync_repository(
                url="https://example.com/repo.git",
                path=repo_path,
            )

        assert result.action == "cloned"
        assert result.commit_sha == "abc123"
        mock_clone.assert_called_once()

    @pytest.mark.asyncio
    async def test_sync_repository_pull(self, tmp_path):
        """Test syncing a repository that exists (pull)."""
        mock_client = MagicMock()
        service = RepositoryService(
            client=mock_client,
            workspace_root=tmp_path,
        )

        # Create existing repo structure
        repo_path = tmp_path / "existing-repo"
        repo_path.mkdir()
        (repo_path / ".git").mkdir()

        with patch('computor_agent.services.repositories.GitRepository') as MockGitRepo:
            mock_repo = MagicMock()
            mock_commit = MagicMock()
            mock_commit.sha = "def456"
            mock_repo.head.return_value = mock_commit
            MockGitRepo.return_value = mock_repo

            result = await service.sync_repository(
                url="https://example.com/repo.git",
                path=repo_path,
            )

        assert result.action == "pulled"
        assert result.commit_sha == "def456"
        mock_repo.pull.assert_called_once()

    @pytest.mark.asyncio
    async def test_sync_review_repository_no_url(self):
        """Test syncing review repository with no URL."""
        mock_client = MagicMock()
        service = RepositoryService(client=mock_client)

        mock_group = MagicMock()
        mock_group.id = "group-123"
        mock_group.properties = None

        result = await service.sync_review_repository(mock_group)

        assert result.action == "skipped"
        assert result.error == "No repository URL in submission group"
        assert result.submission_group_id == "group-123"

    @pytest.mark.asyncio
    async def test_sync_review_repository_with_full_path(self, tmp_path):
        """Test syncing review repository uses full_path for naming."""
        mock_client = MagicMock()
        service = RepositoryService(
            client=mock_client,
            workspace_root=tmp_path,
        )

        mock_group = MagicMock()
        mock_group.id = "group-123"
        mock_group.properties = {
            "repository": {
                "clone_url": "https://gitlab.example.com/course/student.git",
                "full_path": "course/student",
            }
        }

        with patch.object(service, 'sync_repository') as mock_sync:
            mock_sync.return_value = SyncResult(
                path=tmp_path / "review" / "repositories" / "course.student",
                url="https://gitlab.example.com/course/student.git",
                action="cloned",
            )

            result = await service.sync_review_repository(mock_group)

        # Should use full_path with dots
        expected_path = tmp_path / "review" / "repositories" / "course.student"
        mock_sync.assert_called_once()
        call_args = mock_sync.call_args
        assert call_args[1]["path"] == expected_path

    @pytest.mark.asyncio
    async def test_sync_student_repository(self, tmp_path):
        """Test syncing student repository."""
        mock_client = MagicMock()
        service = RepositoryService(
            client=mock_client,
            workspace_root=tmp_path,
        )

        with patch.object(service, 'sync_repository') as mock_sync:
            mock_sync.return_value = SyncResult(
                path=tmp_path / "student" / "my-repo",
                url="https://example.com/repo.git",
                action="cloned",
            )

            result = await service.sync_student_repository(
                url="https://example.com/repo.git",
                full_path="group/my-repo",
            )

        expected_path = tmp_path / "student" / "group.my-repo"
        mock_sync.assert_called_once()
        call_args = mock_sync.call_args
        assert call_args[1]["path"] == expected_path

    @pytest.mark.asyncio
    async def test_sync_reference_repository(self, tmp_path):
        """Test syncing reference repository."""
        mock_client = MagicMock()
        service = RepositoryService(
            client=mock_client,
            workspace_root=tmp_path,
        )

        with patch.object(service, 'sync_repository') as mock_sync:
            mock_sync.return_value = SyncResult(
                path=tmp_path / "reference" / "course-123",
                url="https://example.com/repo.git",
                action="cloned",
            )

            result = await service.sync_reference_repository(
                url="https://example.com/repo.git",
                course_id="course-123",
            )

        expected_path = tmp_path / "reference" / "course-123"
        mock_sync.assert_called_once()
        call_args = mock_sync.call_args
        assert call_args[1]["path"] == expected_path
