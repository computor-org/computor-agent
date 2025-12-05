"""
Services for the Computor Agent.

This module provides high-level services that combine API clients,
Git operations, and credential management for agent workflows.

Directory Structure (matching VSCode extension):
    <workspace_root>/
    ├── .computor                   # Marker file with backend URL
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

Example:
    ```python
    from computor_agent.services import RepositoryService
    from computor_agent.settings import ComputorConfig, GitCredentialsStore
    from computor_client import ComputorClient

    # Setup
    config = ComputorConfig.from_file("~/.computor/config.yaml")
    credentials = GitCredentialsStore.from_file("~/.computor/credentials.yaml")

    async with ComputorClient(base_url=config.backend.url) as client:
        await client.login(
            username=config.backend.username,
            password=config.backend.get_password(),
        )

        # Create repository service
        repo_service = RepositoryService(
            client=client,
            credentials_store=credentials,
            workspace_root=Path("/home/user/computor-workspace"),
        )

        # Ensure directory structure exists
        await repo_service.ensure_directories()

        # Sync all repositories for tutor review
        results = await repo_service.sync_review_repositories(
            course_content_id="content-123",
        )
    ```
"""

from computor_agent.services.repositories import (
    RepositoryService,
    RepositoryType,
    WorkspaceDirectories,
    SyncResult,
    RepositoryInfo,
    slugify,
    derive_repository_name,
)

__all__ = [
    "RepositoryService",
    "RepositoryType",
    "WorkspaceDirectories",
    "SyncResult",
    "RepositoryInfo",
    "slugify",
    "derive_repository_name",
]
