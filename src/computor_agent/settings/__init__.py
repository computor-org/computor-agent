"""
Settings and configuration for Computor Agent.

This module provides configuration management for agent settings,
including Git credentials, API endpoints, and other service configurations.

Example:
    ```python
    from computor_agent.settings import GitCredentialsStore

    # Load credentials from file
    store = GitCredentialsStore.from_file("~/.computor/credentials.yaml")

    # Get credentials for a URL
    creds = store.get_credentials("https://gitlab.example.com/org/repo.git")

    # Use with GitRepository
    from computor_agent.git import GitRepository
    repo = GitRepository.clone(url, path, credentials=creds)
    ```
"""

from computor_agent.settings.credentials import (
    GitCredentialsStore,
    CredentialMapping,
    CredentialScope,
)

__all__ = [
    "GitCredentialsStore",
    "CredentialMapping",
    "CredentialScope",
]
