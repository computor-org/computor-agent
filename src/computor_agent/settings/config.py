"""
Computor Agent configuration.

This module provides configuration management for the Computor Agent,
including backend API settings, user credentials, and agent identity.
"""

import os
import json
import logging
from pathlib import Path
from typing import Any, Optional, Union

import yaml
from pydantic import BaseModel, Field, SecretStr, field_validator

logger = logging.getLogger(__name__)


def load_config_data(path: Union[str, Path]) -> dict:
    """Read a YAML or JSON config file into a dict.

    The format is sniffed from the suffix; unknown suffixes try YAML first,
    then JSON.

    Raises:
        FileNotFoundError: If the file doesn't exist.
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

    return data or {}


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
    busy_retry_delay_seconds: float = Field(
        default=30.0,
        ge=0,
        description=(
            "Seconds to wait between retries when the provider is busy "
            "(rate-limited, timed out, connection refused, or 5xx)."
        ),
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


class CacheConfig(BaseModel):
    """Configuration for data caching.

    Deprecated: the HTTP-polling scheduler that used this cache was removed.
    The section is still accepted in config files for compatibility but is
    ignored at runtime.
    """

    model_config = {"extra": "forbid"}

    enabled: bool = Field(
        default=True,
        description="Deprecated, ignored",
    )
    course_members_ttl_seconds: int = Field(
        default=10800,  # 3 hours
        ge=60,
        le=86400,
        description="Deprecated, ignored",
    )
    course_content_ttl_seconds: int = Field(
        default=300,  # 5 minutes
        ge=30,
        le=3600,
        description="Deprecated, ignored",
    )
    persist_to_file: bool = Field(
        default=False,
        description="Deprecated, ignored",
    )
    cache_dir: Optional[Path] = Field(
        default=None,
        description="Deprecated, ignored",
    )


class SchedulerConfig(BaseModel):
    """Configuration for the agent scheduler (top-level config key: scheduler)."""

    model_config = {"extra": "forbid"}

    enabled: bool = Field(
        default=True,
        description="Enable the scheduler",
    )
    poll_interval_seconds: int = Field(
        default=60,
        ge=5,
        le=3600,
        description=(
            "Interval of the periodic REST catch-up scan that backstops the "
            "WebSocket event stream (seconds)"
        ),
    )
    max_concurrent_processing: int = Field(
        default=5,
        ge=1,
        le=50,
        description=(
            "Maximum concurrent message groups being processed (the worker "
            "count; overridable via COMPUTOR_WORKERS)"
        ),
    )
    cooldown_seconds: int = Field(
        default=60,
        ge=0,
        description="Minimum seconds between processing the same submission group",
    )
    cache: CacheConfig = Field(
        default_factory=CacheConfig,
        description="Deprecated (polling-scheduler cache), accepted but ignored",
    )


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
    vision_llm: Optional[LLMSettings] = Field(
        default=None,
        description=(
            "Secondary vision-capable LLM used only for figure review "
            "(see tutor.figure_review)"
        )
    )
    tutor: Optional[dict[str, Any]] = Field(
        default=None,
        description="Tutor agent configuration (nested under 'tutor' key)"
    )
    scheduler: Optional[SchedulerConfig] = Field(
        default=None,
        description="Scheduler settings (worker count, catch-up interval, cooldown)"
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
        return cls.from_dict(load_config_data(path))

    @classmethod
    def from_dict(cls, data: dict) -> "ComputorConfig":
        """
        Create configuration from a dictionary.

        A legacy top-level ``credentials`` block (Git access tokens used by the
        removed repository-cloning path) is ignored with a warning: submissions
        are now fetched as artifact ZIPs through the backend API, so no Git
        credentials are needed. It is stripped here rather than rejected so that
        older config files keep loading under ``extra: forbid``.

        Args:
            data: Configuration dictionary

        Returns:
            ComputorConfig instance
        """
        if isinstance(data, dict) and "credentials" in data:
            data = {k: v for k, v in data.items() if k != "credentials"}
            logger.warning(
                "Ignoring obsolete 'credentials' section in config: Git "
                "credentials are no longer used (submissions are fetched via "
                "the backend API). Remove this section to silence this warning."
            )
        return cls(**data)

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
            data["llm"] = self._llm_settings_to_dict(self.llm, include_secrets)
        if self.vision_llm:
            data["vision_llm"] = self._llm_settings_to_dict(self.vision_llm, include_secrets)

        return data

    @staticmethod
    def _llm_settings_to_dict(llm: LLMSettings, include_secrets: bool) -> dict:
        """Serialize an LLMSettings block, masking the API key by default."""
        llm_dict = {
            "provider": llm.provider,
            "model": llm.model,
        }
        if llm.base_url:
            llm_dict["base_url"] = llm.base_url
        if llm.api_key:
            llm_dict["api_key"] = llm.get_api_key() if include_secrets else "***"
        if llm.temperature != 0.7:
            llm_dict["temperature"] = llm.temperature
        if llm.max_tokens:
            llm_dict["max_tokens"] = llm.max_tokens
        return llm_dict

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

        # Write with restricted permissions atomically
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, content.encode())
        finally:
            os.close(fd)

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


# Environment variables the container/start-script path can use to override
# values from the config file. YAML stays the base; a set (non-empty) variable
# wins. Every override is re-validated through the same pydantic models as
# file values.
_ENV_OVERRIDE_PATHS: dict[str, tuple[str, str]] = {
    "COMPUTOR_BACKEND_URL": ("backend", "url"),
    "COMPUTOR_BACKEND_API_TOKEN": ("backend", "api_token"),
    "COMPUTOR_BACKEND_USERNAME": ("backend", "username"),
    "COMPUTOR_BACKEND_PASSWORD": ("backend", "password"),
    "COMPUTOR_LLM_PROVIDER": ("llm", "provider"),
    "COMPUTOR_LLM_MODEL": ("llm", "model"),
    "COMPUTOR_LLM_BASE_URL": ("llm", "base_url"),
    "COMPUTOR_LLM_API_KEY": ("llm", "api_key"),
    "COMPUTOR_VISION_LLM_PROVIDER": ("vision_llm", "provider"),
    "COMPUTOR_VISION_LLM_MODEL": ("vision_llm", "model"),
    "COMPUTOR_VISION_LLM_BASE_URL": ("vision_llm", "base_url"),
    "COMPUTOR_VISION_LLM_API_KEY": ("vision_llm", "api_key"),
}


def apply_env_overrides(
    config: ComputorConfig,
    environ: Optional[dict[str, str]] = None,
) -> ComputorConfig:
    """
    Overlay COMPUTOR_* environment variables onto a loaded configuration.

    Supported variables (see _ENV_OVERRIDE_PATHS), plus:
        COMPUTOR_WORKERS -> scheduler.max_concurrent_processing
            (the worker count: how many messages are processed concurrently)

    Args:
        config: Configuration loaded from file
        environ: Environment mapping (defaults to os.environ; injectable for tests)

    Returns:
        A new re-validated ComputorConfig with overrides applied, or the
        original instance when no supported variable is set.

    Raises:
        ValueError: If COMPUTOR_WORKERS is not an integer between 1 and 50.
    """
    env = os.environ if environ is None else environ

    # mode="python" keeps SecretStr values intact so re-validation does not
    # destroy secrets loaded from the file (unlike to_dict, which masks them).
    data = config.model_dump(mode="python")

    changed = False
    for var, (section, key) in _ENV_OVERRIDE_PATHS.items():
        value = env.get(var)
        if not value:
            continue
        if data.get(section) is None:
            data[section] = {}
        data[section][key] = value
        changed = True

    workers = env.get("COMPUTOR_WORKERS")
    if workers:
        try:
            workers_int = int(workers)
        except ValueError as e:
            raise ValueError(
                f"COMPUTOR_WORKERS must be an integer, got {workers!r}"
            ) from e
        if not 1 <= workers_int <= 50:
            raise ValueError(
                f"COMPUTOR_WORKERS must be between 1 and 50, got {workers_int}"
            )
        scheduler = data.get("scheduler") or {}
        scheduler["max_concurrent_processing"] = workers_int
        data["scheduler"] = scheduler
        changed = True

    if not changed:
        return config

    return ComputorConfig.from_dict(data)
