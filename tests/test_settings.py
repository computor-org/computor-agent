"""Tests for settings and credentials store."""

import json
import os
import tempfile
from pathlib import Path

import pytest
import yaml

from computor_agent.settings import (
    GitCredentialsStore,
    CredentialMapping,
    CredentialScope,
    BackendConfig,
    AgentConfig,
    LLMSettings,
    ComputorConfig,
)
from computor_agent.git import GitProvider


class TestCredentialMapping:
    """Tests for CredentialMapping model."""

    def test_create_mapping(self):
        """Test creating a credential mapping."""
        mapping = CredentialMapping(
            pattern="https://gitlab.example.com",
            token="glpat-xxxx",
        )
        assert mapping.pattern == "https://gitlab.example.com"
        assert mapping.get_token() == "glpat-xxxx"
        assert mapping.scope == CredentialScope.HOST  # Auto-inferred

    def test_scope_auto_inference(self):
        """Test that scope is automatically inferred from pattern."""
        # Host scope (no path)
        host = CredentialMapping(pattern="https://gitlab.example.com", token="x")
        assert host.scope == CredentialScope.HOST

        # Group scope (one path segment)
        group = CredentialMapping(pattern="https://gitlab.example.com/group", token="x")
        assert group.scope == CredentialScope.GROUP

        # Project scope (two path segments)
        project = CredentialMapping(pattern="https://gitlab.example.com/group/repo", token="x")
        assert project.scope == CredentialScope.PROJECT

        # Project scope with .git suffix
        project_git = CredentialMapping(
            pattern="https://gitlab.example.com/group/repo.git", token="x"
        )
        assert project_git.scope == CredentialScope.PROJECT

    def test_to_git_credentials(self):
        """Test converting mapping to GitCredentials."""
        mapping = CredentialMapping(
            pattern="https://gitlab.example.com",
            token="glpat-xxxx",
            username="oauth2",
            provider=GitProvider.GITLAB,
        )
        creds = mapping.to_git_credentials()
        assert creds.get_token() == "glpat-xxxx"
        assert creds.username == "oauth2"
        assert creds.provider == GitProvider.GITLAB

    def test_matches_host_scope(self):
        """Test matching with host scope (auto-inferred)."""
        mapping = CredentialMapping(
            pattern="https://gitlab.example.com",
            token="glpat-xxxx",
        )
        # Should match any repo on this host
        assert mapping.matches("https://gitlab.example.com/user/repo.git")
        assert mapping.matches("https://gitlab.example.com/org/project/repo.git")
        assert mapping.matches("https://gitlab.example.com/repo.git")

        # Should not match different hosts
        assert not mapping.matches("https://github.com/user/repo.git")
        assert not mapping.matches("https://other.gitlab.com/user/repo.git")

    def test_matches_group_scope(self):
        """Test matching with group scope (auto-inferred)."""
        mapping = CredentialMapping(
            pattern="https://gitlab.example.com/course-2024",
            token="glpat-xxxx",
        )
        # Should match repos in this group
        assert mapping.matches("https://gitlab.example.com/course-2024/student1.git")
        assert mapping.matches("https://gitlab.example.com/course-2024/subgroup/repo.git")

        # Should not match repos in different groups
        assert not mapping.matches("https://gitlab.example.com/other-course/repo.git")
        assert not mapping.matches("https://gitlab.example.com/repo.git")

    def test_matches_project_scope(self):
        """Test matching with project scope (auto-inferred)."""
        mapping = CredentialMapping(
            pattern="https://gitlab.example.com/course/specific-repo",
            token="glpat-xxxx",
        )
        # Should match exact project
        assert mapping.matches("https://gitlab.example.com/course/specific-repo.git")
        assert mapping.matches("https://gitlab.example.com/course/specific-repo")

        # Should not match other projects
        assert not mapping.matches("https://gitlab.example.com/course/other-repo.git")
        assert not mapping.matches("https://gitlab.example.com/course/specific-repo-2.git")

    def test_match_score(self):
        """Test match scoring for prioritization."""
        host_mapping = CredentialMapping(
            pattern="https://gitlab.example.com",
            token="host-token",
        )
        group_mapping = CredentialMapping(
            pattern="https://gitlab.example.com/course",
            token="group-token",
        )
        project_mapping = CredentialMapping(
            pattern="https://gitlab.example.com/course/repo",
            token="project-token",
        )

        url = "https://gitlab.example.com/course/repo.git"

        # Project should have highest score
        assert project_mapping.match_score(url) > group_mapping.match_score(url)
        assert group_mapping.match_score(url) > host_mapping.match_score(url)
        assert host_mapping.match_score(url) > 0

        # Non-matching should return 0
        assert host_mapping.match_score("https://github.com/user/repo.git") == 0


class TestGitCredentialsStore:
    """Tests for GitCredentialsStore."""

    def test_add_and_get_credentials(self):
        """Test adding and retrieving credentials."""
        store = GitCredentialsStore()
        store.add(
            pattern="https://gitlab.example.com",
            token="glpat-xxxx",
        )

        creds = store.get_credentials("https://gitlab.example.com/user/repo.git")
        assert creds is not None
        assert creds.get_token() == "glpat-xxxx"

    def test_get_credentials_no_match(self):
        """Test getting credentials when no match exists."""
        store = GitCredentialsStore()
        store.add(
            pattern="https://gitlab.example.com",
            token="glpat-xxxx",
        )

        creds = store.get_credentials("https://github.com/user/repo.git")
        assert creds is None

    def test_most_specific_match(self):
        """Test that most specific credential is returned."""
        store = GitCredentialsStore()

        # Add host-level credential (auto-inferred)
        store.add(
            pattern="https://gitlab.example.com",
            token="host-token",
        )

        # Add group-level credential (auto-inferred)
        store.add(
            pattern="https://gitlab.example.com/course",
            token="group-token",
        )

        # Add project-level credential (auto-inferred)
        store.add(
            pattern="https://gitlab.example.com/course/special-repo",
            token="project-token",
        )

        # Should get project token for specific repo
        creds = store.get_credentials("https://gitlab.example.com/course/special-repo.git")
        assert creds.get_token() == "project-token"

        # Should get group token for other repos in group
        creds = store.get_credentials("https://gitlab.example.com/course/other-repo.git")
        assert creds.get_token() == "group-token"

        # Should get host token for repos outside group
        creds = store.get_credentials("https://gitlab.example.com/other/repo.git")
        assert creds.get_token() == "host-token"

    def test_remove_mapping(self):
        """Test removing a credential mapping."""
        store = GitCredentialsStore()
        store.add(
            pattern="https://gitlab.example.com",
            token="glpat-xxxx",
        )

        assert len(store) == 1
        assert store.remove("https://gitlab.example.com")
        assert len(store) == 0

        # Removing non-existent should return False
        assert not store.remove("https://github.com")

    def test_list_mappings(self):
        """Test listing all mappings."""
        store = GitCredentialsStore()
        store.add(pattern="https://gitlab.example.com", token="token1")
        store.add(pattern="https://github.com", token="token2")

        mappings = store.list_mappings()
        assert len(mappings) == 2
        patterns = [m.pattern for m in mappings]
        assert "https://gitlab.example.com" in patterns
        assert "https://github.com" in patterns

    def test_from_dict(self):
        """Test creating store from dictionary."""
        data = {
            "credentials": [
                {
                    "pattern": "https://gitlab.example.com",
                    "token": "glpat-xxxx",
                    "provider": "gitlab",
                },
                {
                    "pattern": "https://github.com",
                    "token": "ghp-xxxx",
                },
            ]
        }

        store = GitCredentialsStore.from_dict(data)
        assert len(store) == 2

        creds = store.get_credentials("https://gitlab.example.com/user/repo.git")
        assert creds.get_token() == "glpat-xxxx"
        assert creds.provider == GitProvider.GITLAB

    def test_to_dict_masks_tokens(self):
        """Test that to_dict masks tokens by default."""
        store = GitCredentialsStore()
        store.add(pattern="https://gitlab.example.com", token="secret-token")

        data = store.to_dict()
        assert data["credentials"][0]["token"] == "***"

    def test_to_dict_includes_tokens(self):
        """Test that to_dict can include tokens when requested."""
        store = GitCredentialsStore()
        store.add(pattern="https://gitlab.example.com", token="secret-token")

        data = store.to_dict(include_tokens=True)
        assert data["credentials"][0]["token"] == "secret-token"

    def test_to_dict_minimal_output(self):
        """Test that to_dict only includes non-default fields."""
        store = GitCredentialsStore()
        store.add(pattern="https://gitlab.example.com", token="token")

        data = store.to_dict(include_tokens=True)
        cred = data["credentials"][0]

        # Should only have pattern and token (provider is default GENERIC)
        assert "pattern" in cred
        assert "token" in cred
        assert "provider" not in cred  # Not included when GENERIC
        assert "username" not in cred
        assert "description" not in cred


class TestGitCredentialsStoreFile:
    """Tests for file-based credentials store."""

    def test_from_yaml_file(self):
        """Test loading from YAML file."""
        yaml_content = """
credentials:
  - pattern: https://gitlab.example.com
    token: glpat-xxxx
    description: Main GitLab instance

  - pattern: https://gitlab.example.com/course-2024
    token: glpat-yyyy
    description: Course submissions
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write(yaml_content)
            f.flush()

            try:
                store = GitCredentialsStore.from_file(f.name)
                assert len(store) == 2

                # Check host-level credential
                creds = store.get_credentials("https://gitlab.example.com/other/repo.git")
                assert creds.get_token() == "glpat-xxxx"

                # Check group-level credential (should take precedence)
                creds = store.get_credentials("https://gitlab.example.com/course-2024/repo.git")
                assert creds.get_token() == "glpat-yyyy"
            finally:
                os.unlink(f.name)

    def test_from_json_file(self):
        """Test loading from JSON file."""
        json_content = {
            "credentials": [
                {
                    "pattern": "https://github.com",
                    "token": "ghp-xxxx",
                }
            ]
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(json_content, f)
            f.flush()

            try:
                store = GitCredentialsStore.from_file(f.name)
                assert len(store) == 1

                creds = store.get_credentials("https://github.com/user/repo.git")
                assert creds.get_token() == "ghp-xxxx"
            finally:
                os.unlink(f.name)

    def test_from_file_not_found(self):
        """Test error when file doesn't exist."""
        with pytest.raises(FileNotFoundError):
            GitCredentialsStore.from_file("/nonexistent/path/credentials.yaml")

    def test_save_yaml(self):
        """Test saving to YAML file."""
        store = GitCredentialsStore()
        store.add(
            pattern="https://gitlab.example.com",
            token="glpat-xxxx",
            description="Test credential",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "credentials.yaml"
            store.save(path, format="yaml")

            # Verify file was created with restricted permissions
            assert path.exists()
            assert (path.stat().st_mode & 0o777) == 0o600

            # Verify content
            loaded = GitCredentialsStore.from_file(path)
            assert len(loaded) == 1
            creds = loaded.get_credentials("https://gitlab.example.com/repo.git")
            assert creds.get_token() == "glpat-xxxx"

    def test_save_json(self):
        """Test saving to JSON file."""
        store = GitCredentialsStore()
        store.add(
            pattern="https://github.com",
            token="ghp-xxxx",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "credentials.json"
            store.save(path, format="json")

            # Verify content is valid JSON
            content = path.read_text()
            data = json.loads(content)
            assert "credentials" in data
            assert len(data["credentials"]) == 1


class TestGitCredentialsStoreEnv:
    """Tests for environment-based credentials store."""

    def test_from_env(self):
        """Test loading credentials from environment variables."""
        # Set environment variables
        os.environ["GIT_CRED_0_PATTERN"] = "https://gitlab.example.com"
        os.environ["GIT_CRED_0_TOKEN"] = "glpat-xxxx"

        os.environ["GIT_CRED_1_PATTERN"] = "https://github.com"
        os.environ["GIT_CRED_1_TOKEN"] = "ghp-xxxx"

        try:
            store = GitCredentialsStore.from_env()
            assert len(store) == 2

            creds = store.get_credentials("https://gitlab.example.com/user/repo.git")
            assert creds.get_token() == "glpat-xxxx"

            creds = store.get_credentials("https://github.com/user/repo.git")
            assert creds.get_token() == "ghp-xxxx"
        finally:
            # Clean up
            for key in list(os.environ.keys()):
                if key.startswith("GIT_CRED_"):
                    del os.environ[key]

    def test_from_env_custom_prefix(self):
        """Test loading with custom prefix."""
        os.environ["MY_CRED_0_PATTERN"] = "https://gitlab.example.com"
        os.environ["MY_CRED_0_TOKEN"] = "custom-token"

        try:
            store = GitCredentialsStore.from_env(prefix="MY_CRED_")
            assert len(store) == 1

            creds = store.get_credentials("https://gitlab.example.com/repo.git")
            assert creds.get_token() == "custom-token"
        finally:
            del os.environ["MY_CRED_0_PATTERN"]
            del os.environ["MY_CRED_0_TOKEN"]

    def test_from_env_empty(self):
        """Test loading when no env vars are set."""
        # Clean any existing vars
        for key in list(os.environ.keys()):
            if key.startswith("GIT_CRED_"):
                del os.environ[key]

        store = GitCredentialsStore.from_env()
        assert len(store) == 0


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

    def test_from_env(self):
        """Test loading config from environment variables."""
        os.environ["COMPUTOR_BACKEND_URL"] = "https://api.example.com"
        os.environ["COMPUTOR_BACKEND_USERNAME"] = "tutor"
        os.environ["COMPUTOR_BACKEND_PASSWORD"] = "secret"
        os.environ["COMPUTOR_AGENT_NAME"] = "Env Agent"
        os.environ["COMPUTOR_LLM_PROVIDER"] = "openai"
        os.environ["COMPUTOR_LLM_MODEL"] = "gpt-4"

        try:
            config = ComputorConfig.from_env()
            assert config.backend.url == "https://api.example.com"
            assert config.backend.username == "tutor"
            assert config.backend.get_password() == "secret"
            assert config.agent.name == "Env Agent"
            assert config.llm.provider == "openai"
            assert config.llm.model == "gpt-4"
        finally:
            # Clean up
            for key in list(os.environ.keys()):
                if key.startswith("COMPUTOR_"):
                    del os.environ[key]

    def test_from_env_missing_required(self):
        """Test error when required env vars are missing."""
        # Clean any existing vars
        for key in list(os.environ.keys()):
            if key.startswith("COMPUTOR_"):
                del os.environ[key]

        with pytest.raises(ValueError, match="Missing required"):
            ComputorConfig.from_env()

    def test_from_env_custom_prefix(self):
        """Test loading with custom prefix."""
        os.environ["MY_APP_BACKEND_URL"] = "https://api.example.com"
        os.environ["MY_APP_BACKEND_USERNAME"] = "user"
        os.environ["MY_APP_BACKEND_PASSWORD"] = "pass"

        try:
            config = ComputorConfig.from_env(prefix="MY_APP_")
            assert config.backend.url == "https://api.example.com"
        finally:
            for key in list(os.environ.keys()):
                if key.startswith("MY_APP_"):
                    del os.environ[key]
