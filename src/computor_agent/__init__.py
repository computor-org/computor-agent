"""
Computor Agent - AI agents for course management.

This package provides AI agent capabilities for the Computor course
management system, including a tutor AI for grading student submissions.
"""

__version__ = "0.1.0"

from computor_agent.llm import (
    DummyProvider,
    DummyProviderConfig,
    LLMConfig,
    LLMProvider,
    LLMResponse,
    Message,
    MessageRole,
    OpenAIProvider,
    ProviderType,
    StreamChunk,
    create_provider,
    get_provider,
    list_providers,
)

from computor_agent.git import (
    GitRepository,
    GitCredentials,
    GitProvider,
    GitError,
    RepositoryNotFoundError,
    CloneError,
    CommitError,
    FileStatus,
    FileChange,
    RepoStatus,
    Commit,
    Branch,
    Diff,
    Author,
)

from computor_agent.settings import (
    GitCredentialsStore,
    CredentialMapping,
    CredentialScope,
)

__all__ = [
    # Version
    "__version__",
    # LLM Config
    "LLMConfig",
    "DummyProviderConfig",
    "ProviderType",
    "Message",
    "MessageRole",
    # LLM Base classes
    "LLMProvider",
    "LLMResponse",
    "StreamChunk",
    # LLM Providers
    "OpenAIProvider",
    "DummyProvider",
    # LLM Factory
    "get_provider",
    "create_provider",
    "list_providers",
    # Git
    "GitRepository",
    "GitCredentials",
    "GitProvider",
    "GitError",
    "RepositoryNotFoundError",
    "CloneError",
    "CommitError",
    "FileStatus",
    "FileChange",
    "RepoStatus",
    "Commit",
    "Branch",
    "Diff",
    "Author",
    # Settings
    "GitCredentialsStore",
    "CredentialMapping",
    "CredentialScope",
]
