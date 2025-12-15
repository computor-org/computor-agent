"""
Computor Agent configuration.

This module provides configuration management for the Computor Agent,
including backend API settings, user credentials, and agent identity.
"""

import os
import json
from pathlib import Path
from typing import Any, Optional, Union

import yaml
from pydantic import BaseModel, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class BackendConfig(BaseModel):
    """
    Backend API configuration.

    SECURITY: Credentials are protected and will not be exposed in
    string representations, logging, or serialization by default.

    Supports two authentication methods:
    1. API Token (recommended): Set `api_token` field
    2. Basic Auth: Set `username` and `password` fields

    If both are provided, API token takes precedence.

    Example with API token:
        ```python
        config = BackendConfig(
            url="https://api.computor.example.com",
            api_token="ctp_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6",
        )
        ```

    Example with username/password:
        ```python
        config = BackendConfig(
            url="https://api.computor.example.com",
            username="tutor-agent",
            password="secret",
        )
        ```
    """

    model_config = {"extra": "forbid"}

    url: str = Field(
        description="Backend API base URL (e.g., https://api.computor.example.com)"
    )
    api_token: Optional[SecretStr] = Field(
        default=None,
        description="API token for authentication (format: ctp_<32chars>). Preferred over username/password."
    )
    username: Optional[str] = Field(
        default=None,
        description="Username for Basic Auth (used if api_token not set)"
    )
    password: Optional[SecretStr] = Field(
        default=None,
        description="Password for Basic Auth (used if api_token not set)"
    )
    timeout: float = Field(
        default=30.0,
        description="HTTP request timeout in seconds"
    )

    def get_api_token(self) -> Optional[str]:
        """Get the API token as a plain string. Internal use only."""
        if self.api_token:
            return self.api_token.get_secret_value()
        return None

    def get_password(self) -> Optional[str]:
        """Get the password as a plain string. Internal use only."""
        if self.password:
            return self.password.get_secret_value()
        return None

    @property
    def auth_method(self) -> str:
        """Return the authentication method being used."""
        if self.api_token:
            return "api_token"
        elif self.username and self.password:
            return "basic"
        return "none"

    @field_validator("url")
    @classmethod
    def normalize_url(cls, v: str) -> str:
        """Normalize URL by removing trailing slash."""
        return v.rstrip("/")

    def model_post_init(self, __context) -> None:
        """Validate that at least one auth method is configured."""
        if not self.api_token and not (self.username and self.password):
            raise ValueError(
                "Either api_token or both username and password must be provided"
            )

    def __repr__(self) -> str:
        """Safe representation that hides credentials."""
        if self.api_token:
            return f"BackendConfig(url={self.url!r}, api_token='***')"
        return f"BackendConfig(url={self.url!r}, username={self.username!r}, password='***')"

    def __str__(self) -> str:
        """Safe string representation."""
        return f"BackendConfig(url={self.url}, auth={self.auth_method})"


class AgentConfig(BaseModel):
    """
    Agent identity and behavior configuration.

    Example:
        ```python
        config = AgentConfig(
            name="Tutor AI",
            description="Automated grading assistant",
        )
        ```
    """

    name: str = Field(
        default="Computor Agent",
        description="Agent display name"
    )
    description: Optional[str] = Field(
        default=None,
        description="Agent description"
    )


class LLMSettings(BaseModel):
    """
    LLM provider settings.

    SECURITY: API keys are protected and will not be exposed in
    string representations, logging, or serialization by default.

    Example:
        ```python
        settings = LLMSettings(
            provider="openai",
            model="gpt-oss-120b",
            base_url="http://localhost:11434/v1",
        )
        ```
    """

    model_config = {"extra": "forbid"}

    provider: str = Field(
        default="openai",
        description="LLM provider type (openai, ollama, lmstudio, dummy)"
    )
    model: str = Field(
        default="gpt-4",
        description="Model name to use"
    )
    base_url: Optional[str] = Field(
        default=None,
        description="Base URL for API (for local providers)"
    )
    api_key: Optional[SecretStr] = Field(
        default=None,
        description="API key (if required)"
    )
    temperature: float = Field(
        default=0.7,
        ge=0.0,
        le=2.0,
        description="Sampling temperature"
    )
    max_tokens: Optional[int] = Field(
        default=None,
        description="Maximum tokens to generate"
    )

    def get_api_key(self) -> Optional[str]:
        """Get the API key as a plain string. Internal use only."""
        if self.api_key:
            return self.api_key.get_secret_value()
        return None

    def __repr__(self) -> str:
        """Safe representation that hides API key."""
        api_key_str = "'***'" if self.api_key else "None"
        return (
            f"LLMSettings(provider={self.provider!r}, model={self.model!r}, "
            f"api_key={api_key_str})"
        )

    def __str__(self) -> str:
        """Safe string representation."""
        return f"LLMSettings(provider={self.provider}, model={self.model})"


class ComputorConfig(BaseModel):
    """
    Complete Computor Agent configuration.

    Combines backend, agent, LLM, credentials, and tutor settings into a single
    configuration object. This is the unified configuration file format.

    SECURITY: This configuration contains sensitive credentials (passwords, API keys).
    - String representations (__repr__, __str__) mask all secrets
    - model_dump() masks secrets by default (use include_secrets=True if needed)
    - Pydantic's default JSON serialization masks SecretStr values

    Example:
        ```python
        config = ComputorConfig(
            backend=BackendConfig(
                url="https://api.computor.example.com",
                api_token="ctp_xxxx",
            ),
            llm=LLMSettings(
                provider="openai",
                model="gpt-oss-120b",
                base_url="http://localhost:11434/v1",
            ),
            credentials=[
                {"pattern": "https://gitlab.example.com", "token": "glpat-xxx"},
            ],
            tutor={
                "grading": {"enabled": True, "auto_submit_grade": True},
            },
        )

        # Load from file
        config = ComputorConfig.from_file("~/.computor/config.yaml")

        # Safe to print - credentials are masked
        print(config)  # Shows "***" for sensitive fields
        ```
    """

    model_config = {"extra": "forbid"}

    backend: BackendConfig = Field(
        description="Backend API configuration"
    )
    agent: AgentConfig = Field(
        default_factory=AgentConfig,
        description="Agent identity configuration"
    )
    llm: Optional[LLMSettings] = Field(
        default=None,
        description="LLM provider settings"
    )
    credentials: Optional[list[dict[str, Any]]] = Field(
        default=None,
        description="Git credentials mappings (list of {pattern, token, ...})"
    )
    tutor: Optional[dict[str, Any]] = Field(
        default=None,
        description="Tutor agent configuration (nested under 'tutor' key)"
    )

    def __repr__(self) -> str:
        """Safe representation that hides all credentials."""
        return (
            f"ComputorConfig(backend={self.backend!r}, "
            f"agent={self.agent!r}, llm={self.llm!r})"
        )

    def __str__(self) -> str:
        """Safe string representation."""
        return (
            f"ComputorConfig(backend_url={self.backend.url}, "
            f"agent={self.agent.name})"
        )

    @classmethod
    def from_file(cls, path: Union[str, Path]) -> "ComputorConfig":
        """
        Load configuration from a YAML or JSON file.

        File format (YAML):
            ```yaml
            backend:
              url: https://api.computor.example.com
              username: tutor-agent
              password: secret-password
              timeout: 30

            agent:
              name: Tutor AI
              description: Automated grading assistant

            llm:
              provider: openai
              model: gpt-oss-120b
              base_url: http://localhost:11434/v1
              temperature: 0.7
            ```

        Args:
            path: Path to configuration file

        Returns:
            Loaded ComputorConfig instance

        Raises:
            FileNotFoundError: If the config file doesn't exist
        """
        path = Path(path).expanduser().resolve()

        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {path}")

        content = path.read_text()

        if path.suffix in (".yaml", ".yml"):
            data = yaml.safe_load(content)
        elif path.suffix == ".json":
            data = json.loads(content)
        else:
            # Try YAML first, then JSON
            try:
                data = yaml.safe_load(content)
            except Exception:
                data = json.loads(content)

        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict) -> "ComputorConfig":
        """
        Create configuration from a dictionary.

        Args:
            data: Configuration dictionary

        Returns:
            ComputorConfig instance
        """
        return cls(**data)

    @classmethod
    def from_env(cls, prefix: str = "COMPUTOR_") -> "ComputorConfig":
        """
        Load configuration from environment variables.

        Environment variables:
            COMPUTOR_BACKEND_URL - Backend API URL
            COMPUTOR_BACKEND_API_TOKEN - API token (preferred, format: ctp_<32chars>)
            COMPUTOR_BACKEND_USERNAME - API username (for basic auth)
            COMPUTOR_BACKEND_PASSWORD - API password (for basic auth)
            COMPUTOR_BACKEND_TIMEOUT - Request timeout

            COMPUTOR_AGENT_NAME - Agent name
            COMPUTOR_AGENT_DESCRIPTION - Agent description

            COMPUTOR_LLM_PROVIDER - LLM provider type
            COMPUTOR_LLM_MODEL - Model name
            COMPUTOR_LLM_BASE_URL - LLM API base URL
            COMPUTOR_LLM_API_KEY - LLM API key
            COMPUTOR_LLM_TEMPERATURE - Sampling temperature
            COMPUTOR_LLM_MAX_TOKENS - Max tokens

        Args:
            prefix: Environment variable prefix

        Returns:
            ComputorConfig instance

        Raises:
            ValueError: If required environment variables are missing
        """
        # Backend config (required)
        backend_url = os.environ.get(f"{prefix}BACKEND_URL")
        backend_api_token = os.environ.get(f"{prefix}BACKEND_API_TOKEN")
        backend_username = os.environ.get(f"{prefix}BACKEND_USERNAME")
        backend_password = os.environ.get(f"{prefix}BACKEND_PASSWORD")

        if not backend_url:
            raise ValueError(f"Missing required environment variable: {prefix}BACKEND_URL")

        # Check for valid auth configuration
        has_api_token = bool(backend_api_token)
        has_basic_auth = bool(backend_username and backend_password)

        if not has_api_token and not has_basic_auth:
            raise ValueError(
                f"Missing authentication: set {prefix}BACKEND_API_TOKEN "
                f"or both {prefix}BACKEND_USERNAME and {prefix}BACKEND_PASSWORD"
            )

        backend = BackendConfig(
            url=backend_url,
            api_token=backend_api_token,
            username=backend_username,
            password=backend_password,
            timeout=float(os.environ.get(f"{prefix}BACKEND_TIMEOUT", "30")),
        )

        # Agent config (optional)
        agent = AgentConfig(
            name=os.environ.get(f"{prefix}AGENT_NAME", "Computor Agent"),
            description=os.environ.get(f"{prefix}AGENT_DESCRIPTION"),
        )

        # LLM config (optional)
        llm = None
        llm_provider = os.environ.get(f"{prefix}LLM_PROVIDER")
        if llm_provider:
            llm = LLMSettings(
                provider=llm_provider,
                model=os.environ.get(f"{prefix}LLM_MODEL", "gpt-4"),
                base_url=os.environ.get(f"{prefix}LLM_BASE_URL"),
                api_key=os.environ.get(f"{prefix}LLM_API_KEY"),
                temperature=float(os.environ.get(f"{prefix}LLM_TEMPERATURE", "0.7")),
                max_tokens=int(os.environ.get(f"{prefix}LLM_MAX_TOKENS"))
                if os.environ.get(f"{prefix}LLM_MAX_TOKENS")
                else None,
            )

        return cls(backend=backend, agent=agent, llm=llm)

    def to_dict(self, include_secrets: bool = False) -> dict:
        """
        Export configuration to a dictionary.

        Args:
            include_secrets: If True, include passwords and API keys (DANGER!)

        Returns:
            Dictionary representation
        """
        backend_dict = {
            "url": self.backend.url,
            "timeout": self.backend.timeout,
        }

        # Include auth credentials based on method used
        if self.backend.api_token:
            backend_dict["api_token"] = self.backend.get_api_token() if include_secrets else "***"
        if self.backend.username:
            backend_dict["username"] = self.backend.username
        if self.backend.password:
            backend_dict["password"] = self.backend.get_password() if include_secrets else "***"

        data = {
            "backend": backend_dict,
            "agent": {
                "name": self.agent.name,
            },
        }

        if self.agent.description:
            data["agent"]["description"] = self.agent.description

        if self.llm:
            data["llm"] = {
                "provider": self.llm.provider,
                "model": self.llm.model,
            }
            if self.llm.base_url:
                data["llm"]["base_url"] = self.llm.base_url
            if self.llm.api_key:
                data["llm"]["api_key"] = self.llm.get_api_key() if include_secrets else "***"
            if self.llm.temperature != 0.7:
                data["llm"]["temperature"] = self.llm.temperature
            if self.llm.max_tokens:
                data["llm"]["max_tokens"] = self.llm.max_tokens

        return data

    def save(self, path: Union[str, Path], format: str = "yaml") -> None:
        """
        Save configuration to a file.

        WARNING: This saves passwords and API keys to disk.
        Ensure proper file permissions.

        Args:
            path: Output file path
            format: Output format ('yaml' or 'json')
        """
        path = Path(path).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)

        data = self.to_dict(include_secrets=True)

        if format == "yaml":
            content = yaml.dump(data, default_flow_style=False, sort_keys=False)
        else:
            content = json.dumps(data, indent=2)

        # Write with restricted permissions
        path.write_text(content)
        os.chmod(path, 0o600)

    def get_tutor_config(self) -> Any:
        """
        Get TutorConfig from the tutor section.

        Returns:
            TutorConfig instance (defaults if tutor section is not present)

        Note: Import is done lazily to avoid circular imports.
        """
        from computor_agent.tutor.config import TutorConfig

        if self.tutor:
            return TutorConfig.from_dict(self.tutor)
        return TutorConfig()

    def get_credentials_store(self) -> Any:
        """
        Get GitCredentialsStore from the credentials section.

        Returns:
            GitCredentialsStore instance (empty if credentials not present)

        Note: Import is done lazily to avoid circular imports.
        """
        from computor_agent.settings.credentials import GitCredentialsStore

        if self.credentials:
            return GitCredentialsStore.from_dict({"credentials": self.credentials})
        return GitCredentialsStore()
