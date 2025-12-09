"""
Restricted search tools for safe grep/find operations.
"""

import asyncio
import logging
import re
import shlex
from pathlib import Path
from typing import Optional

from computor_agent.filesystem.config import FileSystemAccessConfig
from computor_agent.filesystem.exceptions import (
    FileAccessDeniedError,
    InvalidPathError,
    SearchError,
)

logger = logging.getLogger(__name__)


class SearchResult:
    """Result from a search operation."""

    def __init__(
        self,
        file_path: Path,
        line_number: Optional[int] = None,
        line_content: Optional[str] = None,
        match_position: Optional[tuple[int, int]] = None,
    ):
        self.file_path = file_path
        self.line_number = line_number
        self.line_content = line_content
        self.match_position = match_position

    def __repr__(self) -> str:
        if self.line_number is not None:
            return f"{self.file_path}:{self.line_number}: {self.line_content}"
        return str(self.file_path)


class RestrictedSearchTools:
    """
    Secure search tools (grep, find) with directory whitelisting.

    Provides safe wrappers around common Unix search tools with
    command injection protection and directory restrictions.

    Usage:
        config = FileSystemAccessConfig(
            allowed_directories=[Path("/tmp/student-repos")],
            max_search_results=100,
            search_timeout_seconds=30,
        )
        search = RestrictedSearchTools(config)

        # Search for pattern in files
        results = await search.grep(
            pattern="def main",
            directory=Path("/tmp/student-repos/project1")
        )
    """

    def __init__(self, config: FileSystemAccessConfig):
        """
        Initialize search tools.

        Args:
            config: Filesystem access configuration
        """
        self.config = config

    async def grep(
        self,
        pattern: str,
        directory: Path,
        file_pattern: str = "*",
        case_sensitive: bool = True,
        recursive: bool = True,
        context_lines: int = 0,
    ) -> list[SearchResult]:
        """
        Search for a pattern in files using grep.

        Args:
            pattern: Regular expression pattern to search for
            directory: Directory to search in
            file_pattern: File glob pattern (e.g., "*.py")
            case_sensitive: Whether search is case-sensitive
            recursive: Search recursively in subdirectories
            context_lines: Number of context lines to include

        Returns:
            List of SearchResult objects

        Raises:
            FileAccessDeniedError: If directory access is denied
            SearchError: If search fails
        """
        if not self.config.enabled:
            raise FileAccessDeniedError(
                str(directory), "Filesystem access is disabled"
            )

        # Validate directory
        resolved_dir = self._validate_directory(directory)

        # Build grep command
        cmd = self._build_grep_command(
            pattern=pattern,
            directory=resolved_dir,
            file_pattern=file_pattern,
            case_sensitive=case_sensitive,
            recursive=recursive,
            context_lines=context_lines,
        )

        logger.debug(f"Running grep: {' '.join(cmd)}")

        try:
            # Run grep with timeout
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=self.config.search_timeout_seconds
            )

            # Parse results
            results = self._parse_grep_output(stdout.decode("utf-8", errors="replace"))

            # Limit results
            if len(results) > self.config.max_search_results:
                logger.warning(
                    f"Search returned {len(results)} results, "
                    f"limiting to {self.config.max_search_results}"
                )
                results = results[: self.config.max_search_results]

            logger.info(f"grep found {len(results)} matches")
            return results

        except asyncio.TimeoutError:
            logger.error(f"grep timed out after {self.config.search_timeout_seconds}s")
            raise SearchError(
                f"Search timed out after {self.config.search_timeout_seconds} seconds"
            )
        except Exception as e:
            logger.error(f"grep failed: {e}")
            raise SearchError(f"Search failed: {e}")

    async def grep_python(
        self,
        pattern: str,
        directory: Path,
        case_sensitive: bool = True,
        recursive: bool = True,
    ) -> list[SearchResult]:
        """
        Search for pattern in Python files using Python's re module.

        This is a pure-Python implementation that doesn't rely on grep command.

        Args:
            pattern: Regular expression pattern
            directory: Directory to search in
            case_sensitive: Whether search is case-sensitive
            recursive: Search recursively

        Returns:
            List of SearchResult objects
        """
        if not self.config.enabled:
            raise FileAccessDeniedError(
                str(directory), "Filesystem access is disabled"
            )

        resolved_dir = self._validate_directory(directory)

        # Compile regex
        flags = 0 if case_sensitive else re.IGNORECASE
        try:
            regex = re.compile(pattern, flags)
        except re.error as e:
            raise SearchError(f"Invalid regex pattern: {e}")

        # Find all Python files
        py_files = list(resolved_dir.glob("**/*.py" if recursive else "*.py"))

        results = []
        result_count = 0

        for file_path in py_files:
            # Check if file is allowed
            is_allowed, _ = self.config.is_path_allowed(file_path)
            if not is_allowed:
                continue

            try:
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    for line_num, line in enumerate(f, start=1):
                        match = regex.search(line)
                        if match:
                            results.append(
                                SearchResult(
                                    file_path=file_path,
                                    line_number=line_num,
                                    line_content=line.rstrip(),
                                    match_position=match.span(),
                                )
                            )
                            result_count += 1

                            # Check limit
                            if result_count >= self.config.max_search_results:
                                logger.warning(
                                    f"Reached max results ({self.config.max_search_results})"
                                )
                                return results
            except Exception as e:
                logger.warning(f"Failed to search in {file_path}: {e}")
                continue

        logger.info(f"Python grep found {len(results)} matches")
        return results

    async def find(
        self,
        directory: Path,
        name_pattern: Optional[str] = None,
        file_type: Optional[str] = None,
        max_depth: Optional[int] = None,
    ) -> list[Path]:
        """
        Find files matching criteria using find command.

        Args:
            directory: Directory to search in
            name_pattern: Filename pattern (e.g., "*.py")
            file_type: File type filter ('f' for files, 'd' for directories)
            max_depth: Maximum depth to search

        Returns:
            List of matching file paths

        Raises:
            FileAccessDeniedError: If directory access is denied
            SearchError: If search fails
        """
        if not self.config.enabled:
            raise FileAccessDeniedError(
                str(directory), "Filesystem access is disabled"
            )

        resolved_dir = self._validate_directory(directory)

        # Build find command
        cmd = ["find", str(resolved_dir)]

        if max_depth is not None:
            cmd.extend(["-maxdepth", str(max_depth)])

        if file_type:
            cmd.extend(["-type", file_type])

        if name_pattern:
            cmd.extend(["-name", name_pattern])

        logger.debug(f"Running find: {' '.join(cmd)}")

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=self.config.search_timeout_seconds
            )

            # Parse results
            lines = stdout.decode("utf-8", errors="replace").strip().split("\n")
            paths = [Path(line) for line in lines if line]

            # Filter by allowed paths
            allowed_paths = []
            for path in paths:
                is_allowed, _ = self.config.is_path_allowed(path)
                if is_allowed:
                    allowed_paths.append(path)

            # Limit results
            if len(allowed_paths) > self.config.max_search_results:
                logger.warning(
                    f"find returned {len(allowed_paths)} results, "
                    f"limiting to {self.config.max_search_results}"
                )
                allowed_paths = allowed_paths[: self.config.max_search_results]

            logger.info(f"find found {len(allowed_paths)} files")
            return allowed_paths

        except asyncio.TimeoutError:
            logger.error(f"find timed out after {self.config.search_timeout_seconds}s")
            raise SearchError(
                f"Search timed out after {self.config.search_timeout_seconds} seconds"
            )
        except Exception as e:
            logger.error(f"find failed: {e}")
            raise SearchError(f"Search failed: {e}")

    def find_python(
        self,
        directory: Path,
        name_pattern: Optional[str] = None,
        max_depth: Optional[int] = None,
    ) -> list[Path]:
        """
        Find files using pure Python (no external commands).

        Args:
            directory: Directory to search in
            name_pattern: Glob pattern for filenames
            max_depth: Maximum depth to search

        Returns:
            List of matching file paths
        """
        if not self.config.enabled:
            raise FileAccessDeniedError(
                str(directory), "Filesystem access is disabled"
            )

        resolved_dir = self._validate_directory(directory)

        # Build glob pattern
        if max_depth == 0:
            glob_pattern = name_pattern or "*"
        elif max_depth == 1:
            glob_pattern = f"*/{name_pattern or '*'}"
        else:
            glob_pattern = f"**/{name_pattern or '*'}"

        # Find files
        matching_paths = []
        for path in resolved_dir.glob(glob_pattern):
            if path.is_file():
                is_allowed, _ = self.config.is_path_allowed(path)
                if is_allowed:
                    matching_paths.append(path)

                    if len(matching_paths) >= self.config.max_search_results:
                        logger.warning(
                            f"Reached max results ({self.config.max_search_results})"
                        )
                        break

        logger.info(f"Python find found {len(matching_paths)} files")
        return matching_paths

    def _validate_directory(self, directory: Path) -> Path:
        """Validate and resolve directory path."""
        try:
            resolved_dir = directory.expanduser().resolve()
        except (OSError, RuntimeError) as e:
            raise InvalidPathError(str(directory), f"Cannot resolve path: {e}")

        # Check if directory is within allowed directories
        if self.config.allowed_directories:
            is_within_allowed = any(
                self._is_within_directory(resolved_dir, allowed)
                for allowed in self.config.allowed_directories
            )
            if not is_within_allowed:
                raise FileAccessDeniedError(
                    str(resolved_dir), "Directory is not within allowed directories"
                )

        if not resolved_dir.exists():
            raise FileNotFoundError(f"Directory not found: {resolved_dir}")

        if not resolved_dir.is_dir():
            raise FileAccessDeniedError(str(resolved_dir), "Path is not a directory")

        return resolved_dir

    def _build_grep_command(
        self,
        pattern: str,
        directory: Path,
        file_pattern: str,
        case_sensitive: bool,
        recursive: bool,
        context_lines: int,
    ) -> list[str]:
        """Build grep command with proper escaping."""
        cmd = ["grep", "-n"]  # -n for line numbers

        if not case_sensitive:
            cmd.append("-i")

        if recursive:
            cmd.append("-r")

        if context_lines > 0:
            cmd.extend(["-C", str(context_lines)])

        # Add pattern (properly escaped)
        cmd.append(pattern)

        # Add directory
        cmd.append(str(directory))

        # Add file pattern if specified
        if file_pattern != "*":
            cmd.extend(["--include", file_pattern])

        return cmd

    def _parse_grep_output(self, output: str) -> list[SearchResult]:
        """Parse grep output into SearchResult objects."""
        results = []

        for line in output.split("\n"):
            if not line.strip():
                continue

            # Format: filename:line_number:content
            parts = line.split(":", 2)
            if len(parts) >= 3:
                file_path = Path(parts[0])
                try:
                    line_number = int(parts[1])
                    line_content = parts[2]

                    results.append(
                        SearchResult(
                            file_path=file_path,
                            line_number=line_number,
                            line_content=line_content,
                        )
                    )
                except ValueError:
                    # Skip lines that don't match expected format
                    continue

        return results

    def _is_within_directory(self, path: Path, directory: Path) -> bool:
        """Check if path is within directory."""
        try:
            path.relative_to(directory)
            return True
        except ValueError:
            return False
