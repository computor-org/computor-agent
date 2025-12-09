"""
Tests for restricted filesystem access.
"""

import tempfile
from pathlib import Path

import pytest

from computor_agent.filesystem import (
    FileAccessDeniedError,
    FileSizeLimitExceededError,
    FileSystemAccessConfig,
    InvalidPathError,
    RestrictedFileReader,
    RestrictedSearchTools,
    LLMFileSystemTools,
)


@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def config(temp_dir):
    """Create a test filesystem configuration."""
    return FileSystemAccessConfig(
        enabled=True,
        allowed_directories=[temp_dir],
        max_file_size_bytes=1000,
        allowed_extensions=[".py", ".txt"],
        blocked_patterns=[".env", "secret"],
        max_search_results=10,
        search_timeout_seconds=5.0,
    )


@pytest.fixture
def reader(config):
    """Create a RestrictedFileReader instance."""
    return RestrictedFileReader(config)


@pytest.fixture
def search_tools(config):
    """Create a RestrictedSearchTools instance."""
    return RestrictedSearchTools(config)


@pytest.fixture
def llm_tools(config):
    """Create a LLMFileSystemTools instance."""
    return LLMFileSystemTools(config)


class TestFileSystemAccessConfig:
    """Test FileSystemAccessConfig."""

    def test_default_config(self):
        """Test default configuration."""
        config = FileSystemAccessConfig()
        assert config.enabled is True
        assert config.max_file_size_bytes == 10_000_000
        assert config.max_search_results == 100
        assert ".env" in config.blocked_patterns

    def test_path_allowed_within_directory(self, temp_dir, config):
        """Test that files within allowed directories are permitted."""
        test_file = temp_dir / "test.py"
        test_file.write_text("print('hello')")

        is_allowed, reason = config.is_path_allowed(test_file)
        assert is_allowed is True

    def test_path_denied_outside_directory(self, temp_dir, config):
        """Test that files outside allowed directories are denied."""
        outside_file = Path("/tmp/outside.py")

        is_allowed, reason = config.is_path_allowed(outside_file)
        assert is_allowed is False
        assert "not within allowed directories" in reason

    def test_path_denied_blocked_pattern(self, temp_dir, config):
        """Test that files matching blocked patterns are denied."""
        blocked_file = temp_dir / ".env"

        is_allowed, reason = config.is_path_allowed(blocked_file)
        assert is_allowed is False
        assert "blocked pattern" in reason.lower()

    def test_path_denied_wrong_extension(self, temp_dir, config):
        """Test that files with wrong extensions are denied."""
        wrong_ext = temp_dir / "test.exe"

        is_allowed, reason = config.is_path_allowed(wrong_ext)
        assert is_allowed is False
        assert "extension" in reason.lower()

    def test_extension_normalization(self):
        """Test that extensions are normalized with dots."""
        config = FileSystemAccessConfig(allowed_extensions=["py", ".js"])
        assert config.allowed_extensions == [".py", ".js"]


class TestRestrictedFileReader:
    """Test RestrictedFileReader."""

    def test_read_file_success(self, temp_dir, reader):
        """Test reading a valid file."""
        test_file = temp_dir / "test.py"
        content = "print('hello world')"
        test_file.write_text(content)

        result = reader.read_file(test_file)
        assert result == content

    def test_read_file_denied_outside_directory(self, reader):
        """Test that reading outside allowed directories is denied."""
        with pytest.raises(FileAccessDeniedError):
            reader.read_file(Path("/etc/passwd"))

    def test_read_file_denied_blocked_pattern(self, temp_dir, reader):
        """Test that reading blocked patterns is denied."""
        blocked = temp_dir / ".env"
        blocked.write_text("SECRET=123")

        with pytest.raises(FileAccessDeniedError):
            reader.read_file(blocked)

    def test_read_file_size_limit(self, temp_dir, reader):
        """Test that large files are rejected."""
        large_file = temp_dir / "large.txt"
        large_file.write_text("x" * 2000)  # Exceeds 1000 byte limit

        with pytest.raises(FileSizeLimitExceededError):
            reader.read_file(large_file)

    def test_read_file_not_found(self, temp_dir, reader):
        """Test that missing files raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            reader.read_file(temp_dir / "missing.py")

    def test_read_file_safe(self, temp_dir, reader):
        """Test safe read that returns None on error."""
        result = reader.read_file_safe(temp_dir / "missing.py")
        assert result is None

        result = reader.read_file_safe(Path("/etc/passwd"))
        assert result is None

    def test_read_files_multiple(self, temp_dir, reader):
        """Test reading multiple files."""
        file1 = temp_dir / "test1.py"
        file2 = temp_dir / "test2.py"
        file1.write_text("content1")
        file2.write_text("content2")

        results = reader.read_files([file1, file2])
        assert len(results) == 2
        assert results[str(file1)] == "content1"
        assert results[str(file2)] == "content2"

    def test_list_directory(self, temp_dir, reader):
        """Test listing files in a directory."""
        (temp_dir / "file1.py").write_text("content1")
        (temp_dir / "file2.txt").write_text("content2")
        (temp_dir / "file3.exe").write_text("content3")  # Wrong extension

        files = reader.list_directory(temp_dir, recursive=False)
        file_names = [f.name for f in files]

        assert "file1.py" in file_names
        assert "file2.txt" in file_names
        assert "file3.exe" not in file_names  # Filtered by extension

    def test_check_access(self, temp_dir, reader):
        """Test checking file access."""
        test_file = temp_dir / "test.py"
        test_file.write_text("content")

        can_access, reason = reader.check_access(test_file)
        assert can_access is True

        can_access, reason = reader.check_access(Path("/etc/passwd"))
        assert can_access is False


class TestRestrictedSearchTools:
    """Test RestrictedSearchTools."""

    @pytest.mark.asyncio
    async def test_grep_python_simple(self, temp_dir, search_tools):
        """Test Python-based grep for a simple pattern."""
        test_file = temp_dir / "test.py"
        test_file.write_text("def hello():\n    print('world')\n")

        results = await search_tools.grep_python(
            pattern="def",
            directory=temp_dir,
            recursive=False,
        )

        assert len(results) == 1
        assert results[0].line_number == 1
        assert "def hello" in results[0].line_content

    @pytest.mark.asyncio
    async def test_grep_python_case_insensitive(self, temp_dir, search_tools):
        """Test case-insensitive search."""
        test_file = temp_dir / "test.py"
        test_file.write_text("HELLO\nhello\nHeLLo\n")

        results = await search_tools.grep_python(
            pattern="hello",
            directory=temp_dir,
            case_sensitive=False,
        )

        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_grep_python_result_limit(self, temp_dir, search_tools):
        """Test that search results are limited."""
        test_file = temp_dir / "test.py"
        # Create 20 lines matching pattern
        content = "\n".join([f"line {i}" for i in range(20)])
        test_file.write_text(content)

        results = await search_tools.grep_python(
            pattern="line",
            directory=temp_dir,
        )

        # Should be limited to max_search_results (10)
        assert len(results) == 10

    def test_find_python(self, temp_dir, search_tools):
        """Test Python-based find."""
        (temp_dir / "test1.py").write_text("")
        (temp_dir / "test2.py").write_text("")
        (temp_dir / "other.txt").write_text("")

        results = search_tools.find_python(
            directory=temp_dir,
            name_pattern="*.py",
        )

        assert len(results) == 2
        names = [f.name for f in results]
        assert "test1.py" in names
        assert "test2.py" in names
        assert "other.txt" not in names

    def test_validate_directory_denied(self, search_tools):
        """Test that accessing outside directories is denied."""
        with pytest.raises(FileAccessDeniedError):
            search_tools._validate_directory(Path("/etc"))


class TestLLMFileSystemTools:
    """Test LLMFileSystemTools."""

    def test_get_tool_schemas(self, llm_tools):
        """Test getting OpenAI function schemas."""
        schemas = llm_tools.get_tool_schemas()

        assert len(schemas) > 0
        assert any(s["function"]["name"] == "read_file" for s in schemas)
        assert any(s["function"]["name"] == "search_code" for s in schemas)
        assert any(s["function"]["name"] == "find_files" for s in schemas)

    @pytest.mark.asyncio
    async def test_read_file_tool(self, temp_dir, llm_tools):
        """Test read_file tool execution."""
        test_file = temp_dir / "test.py"
        content = "print('hello')"
        test_file.write_text(content)

        result = await llm_tools.execute_tool(
            tool_name="read_file",
            arguments={"path": str(test_file)},
        )

        assert result["success"] is True
        assert result["content"] == content

    @pytest.mark.asyncio
    async def test_read_file_tool_denied(self, llm_tools):
        """Test read_file tool with denied access."""
        result = await llm_tools.execute_tool(
            tool_name="read_file",
            arguments={"path": "/etc/passwd"},
        )

        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_list_files_tool(self, temp_dir, llm_tools):
        """Test list_files tool execution."""
        (temp_dir / "file1.py").write_text("")
        (temp_dir / "file2.txt").write_text("")

        result = await llm_tools.execute_tool(
            tool_name="list_files",
            arguments={"directory": str(temp_dir), "recursive": False},
        )

        assert result["success"] is True
        assert result["count"] == 2

    @pytest.mark.asyncio
    async def test_search_code_tool(self, temp_dir, llm_tools):
        """Test search_code tool execution."""
        test_file = temp_dir / "test.py"
        test_file.write_text("def hello():\n    print('world')\n")

        result = await llm_tools.execute_tool(
            tool_name="search_code",
            arguments={
                "pattern": "def",
                "directory": str(temp_dir),
            },
        )

        assert result["success"] is True
        assert result["count"] == 1
        assert result["matches"][0]["line"] == 1

    @pytest.mark.asyncio
    async def test_find_files_tool(self, temp_dir, llm_tools):
        """Test find_files tool execution."""
        (temp_dir / "test.py").write_text("")
        (temp_dir / "other.txt").write_text("")

        result = await llm_tools.execute_tool(
            tool_name="find_files",
            arguments={
                "directory": str(temp_dir),
                "name_pattern": "*.py",
            },
        )

        assert result["success"] is True
        assert result["count"] == 1

    @pytest.mark.asyncio
    async def test_check_file_access_tool(self, temp_dir, llm_tools):
        """Test check_file_access tool execution."""
        test_file = temp_dir / "test.py"
        test_file.write_text("content")

        result = await llm_tools.execute_tool(
            tool_name="check_file_access",
            arguments={"path": str(test_file)},
        )

        assert result["success"] is True
        assert result["can_access"] is True

    @pytest.mark.asyncio
    async def test_unknown_tool(self, llm_tools):
        """Test that unknown tools raise ValueError."""
        with pytest.raises(ValueError, match="Unknown tool"):
            await llm_tools.execute_tool(
                tool_name="nonexistent_tool",
                arguments={},
            )

    def test_get_summary(self, llm_tools):
        """Test getting configuration summary."""
        summary = llm_tools.get_summary()

        assert "enabled" in summary
        assert "allowed_directories" in summary
        assert "max_file_size_mb" in summary
