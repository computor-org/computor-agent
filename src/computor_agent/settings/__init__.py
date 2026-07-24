"""
Settings and configuration for Computor Agent.

This module provides configuration management for agent settings,
including backend API endpoints, LLM providers, and tutor behaviour.

Example:
    ```python
    from computor_agent.settings import ComputorConfig

    # Load agent configuration
    config = ComputorConfig.from_file("~/.computor/config.yaml")
    print(config.backend.url)
    ```
"""

from computor_agent.settings.config import (
    BackendConfig,
    AgentConfig,
    LLMSettings,
    ComputorConfig,
    apply_env_overrides,
)

__all__ = [
    # Configuration
    "BackendConfig",
    "AgentConfig",
    "LLMSettings",
    "ComputorConfig",
    "apply_env_overrides",
]
