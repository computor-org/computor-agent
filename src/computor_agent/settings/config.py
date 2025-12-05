"""
Computor Agent configuration.

This module provides configuration management for the Computor Agent,
including backend API settings, user credentials, and agent identity.
"""

import os
import json
from pathlib import Path
from typing import Optional, Union

import yaml
from pydantic import BaseModel, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class BackendConfig(BaseModel):
    """
    Backend API configuration.

    SECURITY: Credentials are protected and will not be exposed in
    string representations, logging, or serialization by default.

    Example:
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
    username: str = Field(
        description="Username for API authentication"
    )
    password: SecretStr = Field(
        description="Password for API authentication"
    )
    timeout: float = Field(
        default=30.0,
        description="HTTP request timeout in seconds"
    )

    def get_password(self) -> str:
        """Get the password as a plain string. Internal use only."""
        return self.password.get_secret_value()

    @field_validator("url")
    @classmethod
    def normalize_url(cls, v: str) -> str:
        """Normalize URL by removing trailing slash."""
        return v.rstrip("/")

    def __repr__(self) -> str:
        """Safe representation that hides credentials."""
        return f"BackendConfig(url={self.url!r}, username='***', password='***')"

    def __str__(self) -> str:
        """Safe string representation."""
        return f"BackendConfig(url={self.url})"


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

    Combines backend, agent, and LLM settings into a single configuration object.

    SECURITY: This configuration contains sensitive credentials (passwords, API keys).
    - String representations (__repr__, __str__) mask all secrets
    - model_dump() masks secrets by default (use include_secrets=True if needed)
    - Pydantic's default JSON serialization masks SecretStr values

    Example:
        ```python
        config = ComputorConfig(
            backend=BackendConfig(
                url="https://api.computor.example.com",
                username="tutor-agent",
                password="secret",
            ),
            llm=LLMSettings(
                provider="openai",
                model="gpt-oss-120b",
                base_url="http://localhost:11434/v1",
            ),
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
            COMPUTOR_BACKEND_USERNAME - API username
            COMPUTOR_BACKEND_PASSWORD - API password
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
        backend_username = os.environ.get(f"{prefix}BACKEND_USERNAME")
        backend_password = os.environ.get(f"{prefix}BACKEND_PASSWORD")

        if not all([backend_url, backend_username, backend_password]):
            raise ValueError(
                f"Missing required environment variables: "
                f"{prefix}BACKEND_URL, {prefix}BACKEND_USERNAME, {prefix}BACKEND_PASSWORD"
            )

        backend = BackendConfig(
            url=backend_url,
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
        data = {
            "backend": {
                "url": self.backend.url,
                "username": self.backend.username,
                "password": self.backend.get_password() if include_secrets else "***",
                "timeout": self.backend.timeout,
            },
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
