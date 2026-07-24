"""Tests for settings and configuration models."""

import json
import os
import tempfile
from pathlib import Path

import pytest

from computor_agent.settings import (
    BackendConfig,
    AgentConfig,
    LLMSettings,
    ComputorConfig,
)


class TestBackendConfig:
    """Tests for BackendConfig model."""

    def test_create_backend_config(self):
        """Test creating a backend configuration."""
        config = BackendConfig(
            url="https://api.computor.example.com",
            username="tutor-agent",
            password="secret-password",
        )
        assert config.url == "https://api.computor.example.com"
        assert config.username == "tutor-agent"
        assert config.get_password() == "secret-password"
        assert config.timeout == 30.0  # Default value

    def test_url_normalization(self):
        """Test that trailing slashes are removed from URLs."""
        config = BackendConfig(
            url="https://api.computor.example.com/",
            username="user",
            password="pass",
        )
        assert config.url == "https://api.computor.example.com"

    def test_custom_timeout(self):
        """Test setting a custom timeout."""
        config = BackendConfig(
            url="https://api.example.com",
            username="user",
            password="pass",
            timeout=60.0,
        )
        assert config.timeout == 60.0

    def test_api_token_auth(self):
        """Test creating config with API token authentication."""
        config = BackendConfig(
            url="https://api.example.com",
            api_token="ctp_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6",
        )
        assert config.url == "https://api.example.com"
        assert config.get_api_token() == "ctp_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"
        assert config.auth_method == "api_token"
        assert config.username is None
        assert config.password is None

    def test_basic_auth(self):
        """Test creating config with basic authentication."""
        config = BackendConfig(
            url="https://api.example.com",
            username="user",
            password="pass",
        )
        assert config.auth_method == "basic"
        assert config.api_token is None

    def test_api_token_takes_precedence(self):
        """Test that API token takes precedence when both are provided."""
        config = BackendConfig(
            url="https://api.example.com",
            api_token="ctp_token123",
            username="user",
            password="pass",
        )
        assert config.auth_method == "api_token"

    def test_missing_auth_raises_error(self):
        """Test that missing authentication raises an error."""
        with pytest.raises(ValueError, match="Either api_token or both username and password"):
            BackendConfig(url="https://api.example.com")

    def test_partial_basic_auth_raises_error(self):
        """Test that providing only username (no password) raises an error."""
        with pytest.raises(ValueError, match="Either api_token or both username and password"):
            BackendConfig(url="https://api.example.com", username="user")

    def test_api_token_repr_hides_token(self):
        """Test that repr hides API token."""
        config = BackendConfig(
            url="https://api.example.com",
            api_token="ctp_secret_token_value",
        )
        repr_str = repr(config)
        assert "ctp_secret_token_value" not in repr_str
        assert "***" in repr_str


class TestAgentConfig:
    """Tests for AgentConfig model."""

    def test_default_agent_config(self):
        """Test default agent configuration values."""
        config = AgentConfig()
        assert config.name == "Computor Agent"
        assert config.description is None

    def test_custom_agent_config(self):
        """Test creating agent config with custom values."""
        config = AgentConfig(
            name="Tutor AI",
            description="Automated grading assistant",
        )
        assert config.name == "Tutor AI"
        assert config.description == "Automated grading assistant"


class TestLLMSettings:
    """Tests for LLMSettings model."""

    def test_default_llm_settings(self):
        """Test default LLM settings."""
        settings = LLMSettings()
        assert settings.provider == "openai"
        assert settings.model == "gpt-4"
        assert settings.base_url is None
        assert settings.api_key is None
        assert settings.temperature == 0.7
        assert settings.max_tokens is None

    def test_custom_llm_settings(self):
        """Test creating LLM settings with custom values."""
        settings = LLMSettings(
            provider="ollama",
            model="llama3",
            base_url="http://localhost:11434/v1",
            temperature=0.5,
            max_tokens=4096,
        )
        assert settings.provider == "ollama"
        assert settings.model == "llama3"
        assert settings.base_url == "http://localhost:11434/v1"
        assert settings.temperature == 0.5
        assert settings.max_tokens == 4096

    def test_api_key_handling(self):
        """Test API key secure handling."""
        settings = LLMSettings(api_key="sk-secret-key")
        assert settings.get_api_key() == "sk-secret-key"

        # Without API key
        settings_no_key = LLMSettings()
        assert settings_no_key.get_api_key() is None


class TestComputorConfig:
    """Tests for ComputorConfig model."""

    def test_create_minimal_config(self):
        """Test creating config with only required fields."""
        config = ComputorConfig(
            backend=BackendConfig(
                url="https://api.example.com",
                username="user",
                password="pass",
            )
        )
        assert config.backend.url == "https://api.example.com"
        assert config.agent.name == "Computor Agent"  # Default
        assert config.llm is None  # Optional

    def test_create_full_config(self):
        """Test creating config with all fields."""
        config = ComputorConfig(
            backend=BackendConfig(
                url="https://api.example.com",
                username="tutor",
                password="secret",
                timeout=60.0,
            ),
            agent=AgentConfig(
                name="Tutor AI",
                description="Grading assistant",
            ),
            llm=LLMSettings(
                provider="openai",
                model="gpt-4",
                api_key="sk-xxx",
            ),
        )
        assert config.backend.username == "tutor"
        assert config.agent.name == "Tutor AI"
        assert config.llm.model == "gpt-4"

    def test_from_dict(self):
        """Test creating config from dictionary."""
        data = {
            "backend": {
                "url": "https://api.example.com",
                "username": "user",
                "password": "pass",
            },
            "agent": {
                "name": "Test Agent",
            },
        }
        config = ComputorConfig.from_dict(data)
        assert config.backend.url == "https://api.example.com"
        assert config.agent.name == "Test Agent"

    def test_from_dict_ignores_legacy_credentials(self):
        """A legacy 'credentials' block is stripped, not rejected by extra:forbid."""
        data = {
            "backend": {"url": "https://api.example.com", "api_token": "ctp_" + "a" * 32},
            "credentials": [
                {"pattern": "https://gitlab.example.com", "token": "glpat-x"},
            ],
        }
        # Should load cleanly despite model_config extra="forbid".
        config = ComputorConfig.from_dict(data)
        assert config.backend.url == "https://api.example.com"
        assert not hasattr(config, "credentials")

    def test_to_dict_masks_secrets(self):
        """Test that to_dict masks passwords by default."""
        config = ComputorConfig(
            backend=BackendConfig(
                url="https://api.example.com",
                username="user",
                password="secret-password",
            ),
            llm=LLMSettings(
                api_key="sk-secret-key",
            ),
        )
        data = config.to_dict()
        assert data["backend"]["password"] == "***"
        assert data["llm"]["api_key"] == "***"

    def test_to_dict_includes_secrets(self):
        """Test that to_dict can include secrets when requested."""
        config = ComputorConfig(
            backend=BackendConfig(
                url="https://api.example.com",
                username="user",
                password="secret-password",
            ),
        )
        data = config.to_dict(include_secrets=True)
        assert data["backend"]["password"] == "secret-password"

    def test_vision_llm_optional(self):
        """vision_llm defaults to None and accepts LLMSettings."""
        config = ComputorConfig(
            backend=BackendConfig(
                url="https://api.example.com",
                username="user",
                password="pass",
            ),
        )
        assert config.vision_llm is None

        config = ComputorConfig.from_dict({
            "backend": {
                "url": "https://api.example.com",
                "username": "user",
                "password": "pass",
            },
            "vision_llm": {
                "provider": "ollama",
                "model": "llava:13b",
                "base_url": "http://localhost:11434/v1",
            },
        })
        assert config.vision_llm.provider == "ollama"
        assert config.vision_llm.model == "llava:13b"

    def test_to_dict_vision_llm_masks_api_key(self):
        """vision_llm is serialized like llm, with the API key masked."""
        config = ComputorConfig(
            backend=BackendConfig(
                url="https://api.example.com",
                username="user",
                password="pass",
            ),
            vision_llm=LLMSettings(
                provider="openai",
                model="gpt-4o",
                api_key="sk-vision-secret",
            ),
        )
        data = config.to_dict()
        assert data["vision_llm"]["model"] == "gpt-4o"
        assert data["vision_llm"]["api_key"] == "***"

        data = config.to_dict(include_secrets=True)
        assert data["vision_llm"]["api_key"] == "sk-vision-secret"


class TestComputorConfigFile:
    """Tests for file-based ComputorConfig."""

    def test_from_yaml_file(self):
        """Test loading config from YAML file."""
        yaml_content = """
backend:
  url: https://api.example.com
  username: tutor-agent
  password: secret123

agent:
  name: Tutor AI
  description: Grading assistant

llm:
  provider: openai
  model: gpt-4
  temperature: 0.5
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write(yaml_content)
            f.flush()

            try:
                config = ComputorConfig.from_file(f.name)
                assert config.backend.url == "https://api.example.com"
                assert config.backend.username == "tutor-agent"
                assert config.backend.get_password() == "secret123"
                assert config.agent.name == "Tutor AI"
                assert config.llm.provider == "openai"
                assert config.llm.temperature == 0.5
            finally:
                os.unlink(f.name)

    def test_from_json_file(self):
        """Test loading config from JSON file."""
        json_content = {
            "backend": {
                "url": "https://api.example.com",
                "username": "user",
                "password": "pass",
            }
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(json_content, f)
            f.flush()

            try:
                config = ComputorConfig.from_file(f.name)
                assert config.backend.url == "https://api.example.com"
            finally:
                os.unlink(f.name)

    def test_from_file_not_found(self):
        """Test error when config file doesn't exist."""
        with pytest.raises(FileNotFoundError):
            ComputorConfig.from_file("/nonexistent/path/config.yaml")

    def test_save_yaml(self):
        """Test saving config to YAML file."""
        config = ComputorConfig(
            backend=BackendConfig(
                url="https://api.example.com",
                username="user",
                password="secret",
            ),
            agent=AgentConfig(name="Test Agent"),
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "config.yaml"
            config.save(path, format="yaml")

            # Verify file was created with restricted permissions
            assert path.exists()
            assert (path.stat().st_mode & 0o777) == 0o600

            # Verify content can be loaded back
            loaded = ComputorConfig.from_file(path)
            assert loaded.backend.url == "https://api.example.com"
            assert loaded.backend.get_password() == "secret"

    def test_save_json(self):
        """Test saving config to JSON file."""
        config = ComputorConfig(
            backend=BackendConfig(
                url="https://api.example.com",
                username="user",
                password="secret",
            ),
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "config.json"
            config.save(path, format="json")

            # Verify content is valid JSON
            content = path.read_text()
            data = json.loads(content)
            assert "backend" in data


class TestComputorConfigEnv:
    """Tests for environment-based ComputorConfig."""

    def _base_config(self) -> ComputorConfig:
        from computor_agent.settings.config import ComputorConfig

        return ComputorConfig.from_dict({
            "backend": {"url": "https://api.example.com", "api_token": "ctp_" + "a" * 32},
            "llm": {"provider": "openai", "model": "file-model"},
            "scheduler": {"cooldown_seconds": 42},
        })

    def test_apply_env_overrides_workers(self):
        """COMPUTOR_WORKERS maps to scheduler.max_concurrent_processing
        without disturbing the rest of the config."""
        from computor_agent.settings.config import apply_env_overrides

        config = self._base_config()
        result = apply_env_overrides(config, {"COMPUTOR_WORKERS": "8"})

        assert result.scheduler.max_concurrent_processing == 8
        assert result.scheduler.cooldown_seconds == 42
        assert result.backend.get_api_token() == "ctp_" + "a" * 32

    def test_apply_env_overrides_secrets_stay_secret(self):
        """Overridden and passed-through secrets land as SecretStr."""
        from pydantic import SecretStr

        from computor_agent.settings.config import apply_env_overrides

        config = self._base_config()
        result = apply_env_overrides(
            config,
            {"COMPUTOR_LLM_API_KEY": "sk-test", "COMPUTOR_LLM_MODEL": "env-model"},
        )

        assert isinstance(result.llm.api_key, SecretStr)
        assert result.llm.get_api_key() == "sk-test"
        assert result.llm.model == "env-model"
        assert isinstance(result.backend.api_token, SecretStr)
        assert "sk-test" not in repr(result)

    def test_apply_env_overrides_invalid_workers(self):
        from computor_agent.settings.config import apply_env_overrides

        config = self._base_config()

        with pytest.raises(ValueError, match="must be an integer"):
            apply_env_overrides(config, {"COMPUTOR_WORKERS": "abc"})
        with pytest.raises(ValueError, match="between 1 and 50"):
            apply_env_overrides(config, {"COMPUTOR_WORKERS": "0"})
        with pytest.raises(ValueError, match="between 1 and 50"):
            apply_env_overrides(config, {"COMPUTOR_WORKERS": "51"})

    def test_apply_env_overrides_noop_without_vars(self):
        """No supported variable set: the original instance is returned."""
        from computor_agent.settings.config import apply_env_overrides

        config = self._base_config()
        assert apply_env_overrides(config, {}) is config
        assert apply_env_overrides(config, {"UNRELATED": "x"}) is config

    def test_apply_env_overrides_vision_llm(self):
        """COMPUTOR_VISION_LLM_* creates or patches the vision_llm section."""
        from pydantic import SecretStr

        from computor_agent.settings.config import apply_env_overrides

        # Config without a vision_llm section: env vars create it
        config = self._base_config()
        result = apply_env_overrides(
            config,
            {
                "COMPUTOR_VISION_LLM_PROVIDER": "lmstudio",
                "COMPUTOR_VISION_LLM_MODEL": "qwen2-vl",
                "COMPUTOR_VISION_LLM_BASE_URL": "http://localhost:1234/v1",
                "COMPUTOR_VISION_LLM_API_KEY": "sk-vision",
            },
        )
        assert result.vision_llm.provider == "lmstudio"
        assert result.vision_llm.model == "qwen2-vl"
        assert result.vision_llm.base_url == "http://localhost:1234/v1"
        assert isinstance(result.vision_llm.api_key, SecretStr)
        assert result.vision_llm.get_api_key() == "sk-vision"
        # Main llm untouched
        assert result.llm.model == "file-model"


class TestSecureRepresentations:
    """Tests to ensure credentials are never exposed in string representations."""

    def test_backend_config_repr_hides_credentials(self):
        """Test that BackendConfig repr hides password but shows username."""
        config = BackendConfig(
            url="https://api.example.com",
            username="secret-user",
            password="super-secret-password",
        )
        repr_str = repr(config)
        assert "super-secret-password" not in repr_str
        assert "***" in repr_str
        assert "https://api.example.com" in repr_str
        # Username is shown (it's an identifier, not a secret)
        assert "secret-user" in repr_str

    def test_backend_config_str_hides_credentials(self):
        """Test that BackendConfig str hides password."""
        config = BackendConfig(
            url="https://api.example.com",
            username="secret-user",
            password="super-secret-password",
        )
        str_str = str(config)
        assert "super-secret-password" not in str_str
        # str shows auth method, not individual credentials
        assert "basic" in str_str  # auth_method

    def test_llm_settings_repr_hides_api_key(self):
        """Test that LLMSettings repr hides API key."""
        settings = LLMSettings(
            provider="openai",
            model="gpt-4",
            api_key="sk-super-secret-key-12345",
        )
        repr_str = repr(settings)
        assert "sk-super-secret-key-12345" not in repr_str
        assert "***" in repr_str
        assert "openai" in repr_str
        assert "gpt-4" in repr_str

    def test_llm_settings_str_hides_api_key(self):
        """Test that LLMSettings str hides API key."""
        settings = LLMSettings(
            provider="openai",
            api_key="sk-super-secret-key-12345",
        )
        str_str = str(settings)
        assert "sk-super-secret-key-12345" not in str_str

    def test_computor_config_repr_hides_all_secrets(self):
        """Test that ComputorConfig repr hides all secrets (passwords, api keys)."""
        config = ComputorConfig(
            backend=BackendConfig(
                url="https://api.example.com",
                username="secret-user",
                password="super-secret-password",
            ),
            llm=LLMSettings(
                api_key="sk-secret-key",
            ),
        )
        repr_str = repr(config)
        assert "super-secret-password" not in repr_str
        # Username is shown (it's an identifier, not a secret)
        assert "secret-user" in repr_str
        assert "sk-secret-key" not in repr_str

    def test_computor_config_str_hides_all_secrets(self):
        """Test that ComputorConfig str hides all secrets."""
        config = ComputorConfig(
            backend=BackendConfig(
                url="https://api.example.com",
                username="secret-user",
                password="super-secret-password",
            ),
        )
        str_str = str(config)
        assert "super-secret-password" not in str_str
        assert "secret-user" not in str_str

    def test_to_dict_masks_by_default(self):
        """Test that to_dict masks secrets by default."""
        config = ComputorConfig(
            backend=BackendConfig(
                url="https://api.example.com",
                username="user",
                password="super-secret",
            ),
            llm=LLMSettings(api_key="sk-secret"),
        )
        data = config.to_dict()
        assert data["backend"]["password"] == "***"
        assert data["llm"]["api_key"] == "***"
        # Actual values should not appear anywhere
        assert "super-secret" not in str(data)
        assert "sk-secret" not in str(data)

    def test_print_does_not_expose_secrets(self):
        """Test that printing config does not expose secrets."""
        import io
        import sys

        config = ComputorConfig(
            backend=BackendConfig(
                url="https://api.example.com",
                username="secret-user",
                password="super-secret-password",
            ),
        )

        # Capture print output
        captured = io.StringIO()
        sys.stdout = captured
        print(config)
        sys.stdout = sys.__stdout__

        output = captured.getvalue()
        assert "super-secret-password" not in output
        assert "secret-user" not in output

    def test_format_string_does_not_expose_secrets(self):
        """Test that format strings do not expose secrets."""
        config = ComputorConfig(
            backend=BackendConfig(
                url="https://api.example.com",
                username="secret-user",
                password="super-secret-password",
            ),
        )
        formatted = f"Config: {config}"
        assert "super-secret-password" not in formatted
        assert "secret-user" not in formatted

    def test_logging_does_not_expose_secrets(self):
        """Test that logging config does not expose secrets."""
        import logging
        import io

        config = ComputorConfig(
            backend=BackendConfig(
                url="https://api.example.com",
                username="secret-user",
                password="super-secret-password",
            ),
        )

        # Set up logging to capture output
        log_capture = io.StringIO()
        handler = logging.StreamHandler(log_capture)
        handler.setLevel(logging.DEBUG)
        logger = logging.getLogger("test_secure")
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

        # Log the config
        logger.info(f"Config loaded: {config}")
        logger.debug(f"Backend config: {config.backend}")

        log_output = log_capture.getvalue()
        assert "super-secret-password" not in log_output
        assert "secret-user" not in log_output
