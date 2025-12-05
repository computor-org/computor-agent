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
