"""
Repository service for managing Git repositories.

This module provides high-level operations for cloning and syncing
repositories, matching the directory structure used by the VSCode extension.

Directory Structure:
    <workspace_root>/
    ├── .computor                   # Marker file with metadata
    ├── student/                    # Student repositories
    │   └── <repo-name>/
    ├── review/                     # Tutor review area
    │   ├── repositories/           # Student repos being reviewed
    │   │   └── <repo-name>/
    │   ├── reference/              # Example solutions
    │   │   └── <example-version-id>/
    │   └── submissions/            # Submission artifacts
    │       └── <submission-group-id>/
    │           └── <artifact-id>/
    └── reference/                  # Lecturer reference repos
        └── <course-id>/
"""

import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

from computor_client import ComputorClient
from computor_types.tutor_submission_groups import TutorSubmissionGroupGet

from computor_agent.git import GitRepository, GitCredentials, CloneError, PullError
from computor_agent.settings.credentials import GitCredentialsStore

logger = logging.getLogger(__name__)


class RepositoryType(str, Enum):
    """Type of repository determining storage location."""

    STUDENT = "student"  # Student's own repositories
    REVIEW = "review"  # Student repos being reviewed by tutors
    REVIEW_REFERENCE = "review_reference"  # Example solutions for review
    REFERENCE = "reference"  # Lecturer reference repositories


@dataclass
class WorkspaceDirectories:
    """Workspace directory structure matching VSCode extension."""

    root: Path
    student: Path
    review: Path
    review_repositories: Path
    review_reference: Path
    review_submissions: Path
    reference: Path


@dataclass
class SyncResult:
    """Result of a repository sync operation."""

    path: Path
    url: str
    action: str  # "cloned", "pulled", "skipped", "failed"
    error: Optional[str] = None
    submission_group_id: Optional[str] = None
    commit_sha: Optional[str] = None


@dataclass
class RepositoryInfo:
    """Information about a managed repository."""

    path: Path
    url: str
    repo_type: RepositoryType
    name: str
    submission_group_id: Optional[str] = None
    course_id: Optional[str] = None
    member_names: list[str] = field(default_factory=list)


def slugify(value: Optional[str]) -> Optional[str]:
    """
    Convert a string to a safe directory name.

    Matches the VSCode extension's slugify function.
    """
    if not value:
        return None

    slug = value.strip()
    # Remove .git suffix
    if slug.endswith(".git"):
        slug = slug[:-4]
    # Replace non-alphanumeric chars with hyphens
    slug = re.sub(r"[^a-zA-Z0-9\-_]+", "-", slug)
    # Remove leading/trailing hyphens
    slug = slug.strip("-")
    # Lowercase
    slug = slug.lower()

    return slug if slug else None


def derive_repository_name(
    full_path: Optional[str] = None,
    submission_group_id: Optional[str] = None,
    member_id: Optional[str] = None,
    course_id: Optional[str] = None,
    remote_url: Optional[str] = None,
) -> str:
    """
    Derive a directory name for a repository.

    Matches the VSCode extension's deriveRepositoryDirectoryName function.
    Priority:
    1. full_path with slashes converted to dots
    2. submission_group_id (UUID)
    3. member_id
    4. course_id
    5. slugified name from URL
    """
    # Prefer full_path with dots instead of slashes
    if full_path:
        return full_path.replace("/", ".")

    # Fallback to submission group ID
    if submission_group_id:
        return submission_group_id

    # Fallback to member ID
    if member_id:
        return member_id

    # Fallback to course ID
    if course_id:
        return course_id

    # Last resort: derive from URL
    if remote_url:
        # Try to extract repo name from URL
        try:
            # Handle both URLs and git@ style
            if "://" in remote_url:
                from urllib.parse import urlparse
                parsed = urlparse(remote_url)
                path_parts = [p for p in parsed.path.split("/") if p]
            else:
                # git@host:path format
                path_parts = remote_url.split(":")[-1].split("/")
                path_parts = [p for p in path_parts if p]

            if path_parts:
                name = path_parts[-1]
                slug = slugify(name)
                if slug:
                    return slug
        except Exception:
            pass

    return "repository"


class RepositoryService:
    """
    Service for managing Git repositories for the Computor platform.

    This service provides a unified interface for:
    - Student repositories (student's own work)
    - Review repositories (student repos being reviewed by tutors)
    - Reference repositories (example solutions and lecturer materials)

    The directory structure matches the VSCode extension for compatibility.

    Example:
        ```python
        async with ComputorClient(base_url=config.backend.url) as client:
            await client.login(username, password)

            repo_service = RepositoryService(
                client=client,
                credentials_store=cred_store,
                workspace_root=Path("/home/user/computor-workspace"),
            )

            # Ensure directory structure exists
            await repo_service.ensure_directories()

            # Sync all repositories for tutor review
            results = await repo_service.sync_review_repositories(
                course_content_id="content-123",
            )

            for result in results:
                print(f"{result.action}: {result.path}")
        ```
    """

    def __init__(
        self,
        client: ComputorClient,
        credentials_store: Optional[GitCredentialsStore] = None,
        workspace_root: Optional[Path] = None,
    ):
        """
        Initialize the repository service.

        Args:
            client: Authenticated Computor API client
            credentials_store: Store for Git credentials (optional)
            workspace_root: Root directory for all repositories
        """
        self._client = client
        self._credentials_store = credentials_store or GitCredentialsStore()
        self._workspace_root = Path(workspace_root) if workspace_root else Path.cwd()

    @property
    def workspace_root(self) -> Path:
        """Get the workspace root directory."""
        return self._workspace_root

    @workspace_root.setter
    def workspace_root(self, value: Path) -> None:
        """Set the workspace root directory."""
        self._workspace_root = Path(value)

    def get_directories(self) -> WorkspaceDirectories:
        """
        Get all workspace directories.

        Returns:
            WorkspaceDirectories with all standard paths
        """
        review = self._workspace_root / "review"
        return WorkspaceDirectories(
            root=self._workspace_root,
            student=self._workspace_root / "student",
            review=review,
            review_repositories=review / "repositories",
            review_reference=review / "reference",
            review_submissions=review / "submissions",
            reference=self._workspace_root / "reference",
        )

    async def ensure_directories(self) -> None:
        """Create all workspace directories if they don't exist."""
        dirs = self.get_directories()
        dirs.student.mkdir(parents=True, exist_ok=True)
        dirs.review.mkdir(parents=True, exist_ok=True)
        dirs.review_repositories.mkdir(parents=True, exist_ok=True)
        dirs.review_reference.mkdir(parents=True, exist_ok=True)
        dirs.review_submissions.mkdir(parents=True, exist_ok=True)
        dirs.reference.mkdir(parents=True, exist_ok=True)

    def _get_credentials_for_url(self, url: str) -> Optional[GitCredentials]:
        """Get credentials for a repository URL."""
        return self._credentials_store.get_credentials(url)

    # =========================================================================
    # Path builders (matching VSCode extension)
    # =========================================================================

    def get_student_repo_path(self, repo_name: str) -> Path:
        """Get path for a student repository."""
        return self.get_directories().student / repo_name

    def get_review_repo_path(self, repo_name: str) -> Path:
        """Get path for a review repository (student repo being reviewed)."""
        return self.get_directories().review_repositories / repo_name

    def get_review_reference_path(self, example_version_id: str) -> Path:
        """Get path for a review reference (example solution)."""
        return self.get_directories().review_reference / example_version_id

    def get_review_submission_path(
        self, submission_group_id: str, artifact_id: str
    ) -> Path:
        """Get path for a submission artifact."""
        return (
            self.get_directories().review_submissions
            / submission_group_id
            / artifact_id
        )

    def get_reference_repo_path(self, course_id: str) -> Path:
        """Get path for a lecturer reference repository."""
        return self.get_directories().reference / course_id

    # =========================================================================
    # Marker file (.computor)
    # =========================================================================

    async def get_backend_url(self) -> Optional[str]:
        """Read backend URL from .computor marker file."""
        marker_path = self._workspace_root / ".computor"
        try:
            if not marker_path.exists():
                return None
            content = marker_path.read_text()
            data = json.loads(content)
            return data.get("backendUrl")
        except Exception:
            return None

    async def set_backend_url(self, backend_url: str) -> None:
        """Write backend URL to .computor marker file."""
        marker_path = self._workspace_root / ".computor"
        marker_path.write_text(json.dumps({"backendUrl": backend_url}, indent=2))

    # =========================================================================
    # API operations
    # =========================================================================

    async def get_submission_groups(
        self,
        course_content_id: Optional[str] = None,
        course_id: Optional[str] = None,
        has_submissions: Optional[bool] = None,
    ) -> list[TutorSubmissionGroupGet]:
        """
        Get submission groups from the API (tutor view).

        Args:
            course_content_id: Filter by course content
            course_id: Filter by course
            has_submissions: Filter by whether group has submissions

        Returns:
            List of submission groups
        """
        params = {}
        if course_content_id:
            params["course_content_id"] = course_content_id
        if course_id:
            params["course_id"] = course_id
        if has_submissions is not None:
            params["has_submissions"] = has_submissions

        return await self._client.tutors.get_submission_groups(**params)

    async def get_submission_group(
        self,
        submission_group_id: str,
    ) -> TutorSubmissionGroupGet:
        """Get a specific submission group."""
        return await self._client.tutors.submission_groups(submission_group_id)

    # =========================================================================
    # Repository URL extraction
    # =========================================================================

    def _extract_repository_info(
        self,
        submission_group: TutorSubmissionGroupGet,
    ) -> tuple[Optional[str], Optional[str]]:
        """
        Extract repository URL and full_path from submission group.

        Returns:
            Tuple of (url, full_path)
        """
        if not submission_group.properties:
            return None, None

        url = None
        full_path = None

        # Check for repository URL
        for key in ["repository_url", "repo_url", "git_url", "clone_url"]:
            if key in submission_group.properties:
                value = submission_group.properties[key]
                if isinstance(value, str):
                    url = value
                    break

        # Check for nested repository object
        if not url and "repository" in submission_group.properties:
            repo = submission_group.properties["repository"]
            if isinstance(repo, dict):
                url = repo.get("clone_url") or repo.get("url")
                full_path = repo.get("full_path")

        # Check for full_path directly
        if not full_path and "full_path" in submission_group.properties:
            full_path = submission_group.properties["full_path"]

        return url, full_path

    # =========================================================================
    # Clone and sync operations
    # =========================================================================

    async def clone_repository(
        self,
        url: str,
        path: Path,
        branch: Optional[str] = None,
        depth: Optional[int] = 1,
    ) -> GitRepository:
        """
        Clone a repository with automatic credential injection.

        Args:
            url: Repository URL
            path: Local path to clone to
            branch: Branch to clone (default: default branch)
            depth: Clone depth (default: 1 for shallow clone)

        Returns:
            GitRepository instance

        Raises:
            CloneError: If clone fails
        """
        credentials = self._get_credentials_for_url(url)

        logger.info(f"Cloning repository: {url} -> {path}")

        return GitRepository.clone(
            url=url,
            path=path,
            branch=branch,
            depth=depth,
            credentials=credentials,
        )

    async def sync_repository(
        self,
        url: str,
        path: Path,
        branch: Optional[str] = None,
    ) -> SyncResult:
        """
        Sync a repository (clone if missing, pull if exists).

        Args:
            url: Repository URL
            path: Local path
            branch: Branch to sync

        Returns:
            SyncResult with action taken
        """
        path = Path(path)

        try:
            if path.exists() and (path / ".git").exists():
                # Repository exists, pull updates
                repo = GitRepository(path)
                credentials = self._get_credentials_for_url(url)

                logger.info(f"Pulling updates: {path}")
                repo.pull(credentials=credentials)

                head = repo.head()
                return SyncResult(
                    path=path,
                    url=url,
                    action="pulled",
                    commit_sha=head.sha if head else None,
                )
            else:
                # Clone new repository
                path.parent.mkdir(parents=True, exist_ok=True)
                repo = await self.clone_repository(url, path, branch=branch)

                head = repo.head()
                return SyncResult(
                    path=path,
                    url=url,
                    action="cloned",
                    commit_sha=head.sha if head else None,
                )

        except CloneError as e:
            logger.error(f"Clone failed for {url}: {e}")
            return SyncResult(
                path=path,
                url=url,
                action="failed",
                error=str(e),
            )
        except PullError as e:
            logger.error(f"Pull failed for {path}: {e}")
            return SyncResult(
                path=path,
                url=url,
                action="failed",
                error=str(e),
            )
        except Exception as e:
            logger.exception(f"Unexpected error syncing {url}: {e}")
            return SyncResult(
                path=path,
                url=url,
                action="failed",
                error=str(e),
            )

    # =========================================================================
    # High-level sync operations
    # =========================================================================

    async def sync_review_repository(
        self,
        submission_group: TutorSubmissionGroupGet,
    ) -> SyncResult:
        """
        Sync a single submission group's repository for tutor review.

        Repositories are stored in: review/repositories/<repo-name>/

        Args:
            submission_group: Submission group with repository info

        Returns:
            SyncResult with action taken
        """
        repo_url, full_path = self._extract_repository_info(submission_group)

        if not repo_url:
            return SyncResult(
                path=Path(),
                url="",
                action="skipped",
                error="No repository URL in submission group",
                submission_group_id=submission_group.id,
            )

        # Derive repository name using VSCode extension logic
        repo_name = derive_repository_name(
            full_path=full_path,
            submission_group_id=submission_group.id,
            remote_url=repo_url,
        )

        repo_path = self.get_review_repo_path(repo_name)

        result = await self.sync_repository(url=repo_url, path=repo_path)
        result.submission_group_id = submission_group.id

        return result

    async def sync_review_repositories(
        self,
        course_content_id: Optional[str] = None,
        course_id: Optional[str] = None,
        has_submissions: bool = True,
    ) -> list[SyncResult]:
        """
        Sync all submission repositories for tutor review.

        Repositories are stored in: review/repositories/

        Args:
            course_content_id: Filter by course content
            course_id: Filter by course
            has_submissions: Only sync groups with submissions (default: True)

        Returns:
            List of SyncResults for each repository
        """
        await self.ensure_directories()

        submission_groups = await self.get_submission_groups(
            course_content_id=course_content_id,
            course_id=course_id,
            has_submissions=has_submissions,
        )

        results = []
        for group in submission_groups:
            result = await self.sync_review_repository(group)
            results.append(result)

            if result.action == "cloned":
                logger.info(f"Cloned: {result.path}")
            elif result.action == "pulled":
                logger.info(f"Pulled: {result.path}")
            elif result.action == "failed":
                logger.warning(f"Failed: {result.url} - {result.error}")

        return results

    async def sync_student_repository(
        self,
        url: str,
        full_path: Optional[str] = None,
        submission_group_id: Optional[str] = None,
    ) -> SyncResult:
        """
        Sync a student's own repository.

        Repositories are stored in: student/<repo-name>/

        Args:
            url: Repository URL
            full_path: Full path from repository metadata
            submission_group_id: Submission group ID

        Returns:
            SyncResult with action taken
        """
        await self.ensure_directories()

        repo_name = derive_repository_name(
            full_path=full_path,
            submission_group_id=submission_group_id,
            remote_url=url,
        )

        repo_path = self.get_student_repo_path(repo_name)

        result = await self.sync_repository(url=url, path=repo_path)
        result.submission_group_id = submission_group_id

        return result

    async def sync_reference_repository(
        self,
        url: str,
        course_id: str,
    ) -> SyncResult:
        """
        Sync a lecturer reference repository.

        Repositories are stored in: reference/<course-id>/

        Args:
            url: Repository URL
            course_id: Course ID

        Returns:
            SyncResult with action taken
        """
        await self.ensure_directories()

        repo_path = self.get_reference_repo_path(course_id)

        return await self.sync_repository(url=url, path=repo_path)

    # =========================================================================
    # Listing operations
    # =========================================================================

    def list_student_repositories(self) -> list[Path]:
        """List all student repositories."""
        dirs = self.get_directories()
        return self._list_repos_in_dir(dirs.student)

    def list_review_repositories(self) -> list[Path]:
        """List all review repositories."""
        dirs = self.get_directories()
        return self._list_repos_in_dir(dirs.review_repositories)

    def list_reference_repositories(self) -> list[Path]:
        """List all reference repositories."""
        dirs = self.get_directories()
        return self._list_repos_in_dir(dirs.reference)

    def _list_repos_in_dir(self, directory: Path) -> list[Path]:
        """List all git repositories in a directory."""
        repos = []
        if directory.exists():
            for path in directory.iterdir():
                if path.is_dir() and (path / ".git").exists():
                    repos.append(path)
        return sorted(repos)

    def repository_exists(self, path: Path) -> bool:
        """Check if a repository exists at the given path."""
        return path.exists() and (path / ".git").exists()
