"""
Settings and configuration for Computor Agent.

This module provides configuration management for agent settings,
including Git credentials, API endpoints, and other service configurations.

Example:
    ```python
    from computor_agent.settings import GitCredentialsStore, ComputorConfig

    # Load credentials from file
    store = GitCredentialsStore.from_file("~/.computor/credentials.yaml")

    # Get credentials for a URL
    creds = store.get_credentials("https://gitlab.example.com/org/repo.git")

    # Use with GitRepository
    from computor_agent.git import GitRepository
    repo = GitRepository.clone(url, path, credentials=creds)

    # Load agent configuration
    config = ComputorConfig.from_file("~/.computor/config.yaml")
    print(config.backend.url)
    ```
"""

from computor_agent.settings.credentials import (
    GitCredentialsStore,
    CredentialMapping,
    CredentialScope,
)

from computor_agent.settings.config import (
    BackendConfig,
    AgentConfig,
    LLMSettings,
    ComputorConfig,
)

__all__ = [
    # Credentials
    "GitCredentialsStore",
    "CredentialMapping",
    "CredentialScope",
    # Configuration
    "BackendConfig",
    "AgentConfig",
    "LLMSettings",
    "ComputorConfig",
]
