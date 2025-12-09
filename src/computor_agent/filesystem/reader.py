"""
Restricted file reader for safe LLM access to files.
"""

import logging
from pathlib import Path
from typing import Optional

from computor_agent.filesystem.config import FileSystemAccessConfig
from computor_agent.filesystem.exceptions import (
    FileAccessDeniedError,
    FileSizeLimitExceededError,
    InvalidPathError,
)

logger = logging.getLogger(__name__)


class RestrictedFileReader:
    """
    Secure file reader with path whitelisting and size limits.

    Only allows reading files within configured allowed directories,
    with extension filtering and pattern-based blocking.

    Usage:
        config = FileSystemAccessConfig(
            allowed_directories=[Path("/tmp/student-repos")],
            max_file_size_bytes=1_000_000,
        )
        reader = RestrictedFileReader(config)

        try:
            content = reader.read_file(Path("/tmp/student-repos/main.py"))
        except FileAccessDeniedError as e:
            print(f"Access denied: {e}")
    """

    def __init__(self, config: FileSystemAccessConfig):
        """
        Initialize the file reader.

        Args:
            config: Filesystem access configuration
        """
        self.config = config

    def read_file(self, path: Path, encoding: str = "utf-8") -> str:
        """
        Read a file with security checks.

        Args:
            path: Path to the file to read
            encoding: Text encoding (default: utf-8)

        Returns:
            File contents as string

        Raises:
            FileAccessDeniedError: If access is denied
            FileSizeLimitExceededError: If file is too large
            InvalidPathError: If path is invalid
            FileNotFoundError: If file doesn't exist
            UnicodeDecodeError: If file can't be decoded
        """
        if not self.config.enabled:
            raise FileAccessDeniedError(str(path), "Filesystem access is disabled")

        # Validate path
        try:
            resolved_path = path.expanduser().resolve()
        except (OSError, RuntimeError) as e:
            raise InvalidPathError(str(path), f"Cannot resolve path: {e}")

        # Check if path is allowed
        is_allowed, reason = self.config.is_path_allowed(resolved_path)
        if not is_allowed:
            logger.warning(f"Access denied to {resolved_path}: {reason}")
            raise FileAccessDeniedError(str(resolved_path), reason)

        # Check if file exists
        if not resolved_path.exists():
            raise FileNotFoundError(f"File not found: {resolved_path}")

        if not resolved_path.is_file():
            raise FileAccessDeniedError(
                str(resolved_path), "Path is not a regular file"
            )

        # Check file size
        file_size = resolved_path.stat().st_size
        if file_size > self.config.max_file_size_bytes:
            logger.warning(
                f"File too large: {resolved_path} ({file_size} bytes > "
                f"{self.config.max_file_size_bytes} bytes)"
            )
            raise FileSizeLimitExceededError(
                str(resolved_path), file_size, self.config.max_file_size_bytes
            )

        # Read file
        try:
            content = resolved_path.read_text(encoding=encoding)
            logger.debug(f"Successfully read file: {resolved_path} ({file_size} bytes)")
            return content
        except UnicodeDecodeError as e:
            logger.error(f"Failed to decode file {resolved_path}: {e}")
            raise

    def read_file_safe(
        self, path: Path, encoding: str = "utf-8", fallback: Optional[str] = None
    ) -> Optional[str]:
        """
        Read a file with error handling (returns None on error).

        Args:
            path: Path to the file to read
            encoding: Text encoding (default: utf-8)
            fallback: Value to return on error (default: None)

        Returns:
            File contents or fallback value on error
        """
        try:
            return self.read_file(path, encoding=encoding)
        except Exception as e:
            logger.debug(f"Failed to read file {path}: {e}")
            return fallback

    def read_files(
        self, paths: list[Path], encoding: str = "utf-8"
    ) -> dict[str, str]:
        """
        Read multiple files and return as a dict.

        Files that fail to read are skipped with a warning.

        Args:
            paths: List of file paths to read
            encoding: Text encoding (default: utf-8)

        Returns:
            Dict mapping file path (str) to content
        """
        results = {}

        for path in paths:
            try:
                content = self.read_file(path, encoding=encoding)
                results[str(path)] = content
            except Exception as e:
                logger.warning(f"Skipping file {path}: {e}")
                continue

        return results

    def list_directory(self, directory: Path, recursive: bool = False) -> list[Path]:
        """
        List files in a directory with security checks.

        Args:
            directory: Directory to list
            recursive: If True, list recursively

        Returns:
            List of file paths

        Raises:
            FileAccessDeniedError: If access is denied
            InvalidPathError: If path is invalid
        """
        if not self.config.enabled:
            raise FileAccessDeniedError(
                str(directory), "Filesystem access is disabled"
            )

        # Validate directory
        try:
            resolved_dir = directory.expanduser().resolve()
        except (OSError, RuntimeError) as e:
            raise InvalidPathError(str(directory), f"Cannot resolve path: {e}")

        # Check if directory is allowed
        is_allowed, reason = self.config.is_path_allowed(resolved_dir)
        if not is_allowed:
            logger.warning(f"Access denied to {resolved_dir}: {reason}")
            raise FileAccessDeniedError(str(resolved_dir), reason)

        # Check if directory exists
        if not resolved_dir.exists():
            raise FileNotFoundError(f"Directory not found: {resolved_dir}")

        if not resolved_dir.is_dir():
            raise FileAccessDeniedError(
                str(resolved_dir), "Path is not a directory"
            )

        # List files
        files = []
        pattern = "**/*" if recursive else "*"

        for item in resolved_dir.glob(pattern):
            if item.is_file():
                # Check if file passes all filters
                is_allowed, _ = self.config.is_path_allowed(item)
                if is_allowed:
                    files.append(item)

        logger.debug(f"Listed {len(files)} files in {resolved_dir}")
        return files

    def check_access(self, path: Path) -> tuple[bool, str]:
        """
        Check if a path can be accessed without actually reading it.

        Args:
            path: Path to check

        Returns:
            Tuple of (can_access, reason)
        """
        if not self.config.enabled:
            return False, "Filesystem access is disabled"

        try:
            resolved_path = path.expanduser().resolve()
        except (OSError, RuntimeError) as e:
            return False, f"Invalid path: {e}"

        # Check if path is allowed
        is_allowed, reason = self.config.is_path_allowed(resolved_path)
        if not is_allowed:
            return False, reason

        # Check if exists
        if not resolved_path.exists():
            return False, "File not found"

        if not resolved_path.is_file():
            return False, "Path is not a regular file"

        # Check size
        file_size = resolved_path.stat().st_size
        if file_size > self.config.max_file_size_bytes:
            return False, f"File too large ({file_size} > {self.config.max_file_size_bytes})"

        return True, "Access allowed"
