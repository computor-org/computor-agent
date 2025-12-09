"""
Restricted file writer for safe LLM file and directory creation.
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


class RestrictedFileWriter:
    """
    Secure file writer with path whitelisting and size limits.

    Only allows writing files within configured allowed directories,
    with extension filtering and pattern-based blocking.

    Usage:
        config = FileSystemAccessConfig(
            allowed_directories=[Path("/tmp/student-repos")],
            allow_write=True,
            max_write_size_bytes=1_000_000,
        )
        writer = RestrictedFileWriter(config)

        try:
            writer.write_file(
                Path("/tmp/student-repos/output.txt"),
                "Hello, world!"
            )
        except FileAccessDeniedError as e:
            print(f"Access denied: {e}")
    """

    def __init__(self, config: FileSystemAccessConfig):
        """
        Initialize the file writer.

        Args:
            config: Filesystem access configuration
        """
        self.config = config

    def write_file(
        self,
        path: Path,
        content: str,
        encoding: str = "utf-8",
        create_parents: bool = True,
    ) -> None:
        """
        Write content to a file with security checks.

        Args:
            path: Path to the file to write
            content: Content to write
            encoding: Text encoding (default: utf-8)
            create_parents: Create parent directories if they don't exist

        Raises:
            FileAccessDeniedError: If write access is denied
            FileSizeLimitExceededError: If content is too large
            InvalidPathError: If path is invalid
        """
        if not self.config.enabled:
            raise FileAccessDeniedError(str(path), "Filesystem access is disabled")

        if not self.config.allow_write:
            raise FileAccessDeniedError(str(path), "Write operations are disabled")

        # Validate path
        try:
            resolved_path = path.expanduser().resolve()
        except (OSError, RuntimeError) as e:
            raise InvalidPathError(str(path), f"Cannot resolve path: {e}")

        # Check if path is allowed
        is_allowed, reason = self._check_write_access(resolved_path)
        if not is_allowed:
            logger.warning(f"Write access denied to {resolved_path}: {reason}")
            raise FileAccessDeniedError(str(resolved_path), reason)

        # Check content size
        content_bytes = content.encode(encoding)
        if len(content_bytes) > self.config.max_write_size_bytes:
            logger.warning(
                f"Content too large: {len(content_bytes)} bytes > "
                f"{self.config.max_write_size_bytes} bytes"
            )
            raise FileSizeLimitExceededError(
                str(resolved_path),
                len(content_bytes),
                self.config.max_write_size_bytes,
            )

        # Create parent directories if needed
        if create_parents and not resolved_path.parent.exists():
            # Check if parent directory is allowed
            parent_allowed, parent_reason = self._check_directory_write_access(
                resolved_path.parent
            )
            if not parent_allowed:
                raise FileAccessDeniedError(
                    str(resolved_path.parent),
                    f"Cannot create parent directory: {parent_reason}",
                )
            resolved_path.parent.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Created parent directories for {resolved_path}")

        # Write file
        try:
            resolved_path.write_text(content, encoding=encoding)
            logger.info(
                f"Successfully wrote file: {resolved_path} ({len(content_bytes)} bytes)"
            )
        except Exception as e:
            logger.error(f"Failed to write file {resolved_path}: {e}")
            raise

    def append_file(
        self, path: Path, content: str, encoding: str = "utf-8"
    ) -> None:
        """
        Append content to a file with security checks.

        Args:
            path: Path to the file to append to
            content: Content to append
            encoding: Text encoding (default: utf-8)

        Raises:
            FileAccessDeniedError: If write access is denied
            FileSizeLimitExceededError: If resulting file would be too large
        """
        if not self.config.allow_write:
            raise FileAccessDeniedError(str(path), "Write operations are disabled")

        resolved_path = path.expanduser().resolve()

        # Check write access
        is_allowed, reason = self._check_write_access(resolved_path)
        if not is_allowed:
            raise FileAccessDeniedError(str(resolved_path), reason)

        # Check resulting size
        existing_size = resolved_path.stat().st_size if resolved_path.exists() else 0
        new_content_size = len(content.encode(encoding))
        total_size = existing_size + new_content_size

        if total_size > self.config.max_write_size_bytes:
            raise FileSizeLimitExceededError(
                str(resolved_path), total_size, self.config.max_write_size_bytes
            )

        # Append to file
        try:
            with open(resolved_path, "a", encoding=encoding) as f:
                f.write(content)
            logger.info(f"Successfully appended to file: {resolved_path}")
        except Exception as e:
            logger.error(f"Failed to append to file {resolved_path}: {e}")
            raise

    def create_directory(self, path: Path, parents: bool = True) -> None:
        """
        Create a directory with security checks.

        Args:
            path: Path to the directory to create
            parents: Create parent directories if they don't exist

        Raises:
            FileAccessDeniedError: If write access is denied
            InvalidPathError: If path is invalid
        """
        if not self.config.enabled:
            raise FileAccessDeniedError(str(path), "Filesystem access is disabled")

        if not self.config.allow_write:
            raise FileAccessDeniedError(str(path), "Write operations are disabled")

        # Validate path
        try:
            resolved_path = path.expanduser().resolve()
        except (OSError, RuntimeError) as e:
            raise InvalidPathError(str(path), f"Cannot resolve path: {e}")

        # Check if directory write is allowed
        is_allowed, reason = self._check_directory_write_access(resolved_path)
        if not is_allowed:
            logger.warning(f"Directory creation denied for {resolved_path}: {reason}")
            raise FileAccessDeniedError(str(resolved_path), reason)

        # Create directory
        try:
            resolved_path.mkdir(parents=parents, exist_ok=True)
            logger.info(f"Successfully created directory: {resolved_path}")
        except Exception as e:
            logger.error(f"Failed to create directory {resolved_path}: {e}")
            raise

    def delete_file(self, path: Path) -> None:
        """
        Delete a file with security checks.

        Args:
            path: Path to the file to delete

        Raises:
            FileAccessDeniedError: If delete access is denied
            FileNotFoundError: If file doesn't exist
        """
        if not self.config.enabled:
            raise FileAccessDeniedError(str(path), "Filesystem access is disabled")

        if not self.config.allow_delete:
            raise FileAccessDeniedError(str(path), "Delete operations are disabled")

        resolved_path = path.expanduser().resolve()

        # Check if path is allowed
        is_allowed, reason = self._check_write_access(resolved_path)
        if not is_allowed:
            raise FileAccessDeniedError(str(resolved_path), reason)

        if not resolved_path.exists():
            raise FileNotFoundError(f"File not found: {resolved_path}")

        if not resolved_path.is_file():
            raise FileAccessDeniedError(
                str(resolved_path), "Path is not a regular file"
            )

        # Delete file
        try:
            resolved_path.unlink()
            logger.info(f"Successfully deleted file: {resolved_path}")
        except Exception as e:
            logger.error(f"Failed to delete file {resolved_path}: {e}")
            raise

    def delete_directory(self, path: Path, recursive: bool = False) -> None:
        """
        Delete a directory with security checks.

        Args:
            path: Path to the directory to delete
            recursive: If True, delete directory and all contents

        Raises:
            FileAccessDeniedError: If delete access is denied
            FileNotFoundError: If directory doesn't exist
        """
        if not self.config.enabled:
            raise FileAccessDeniedError(str(path), "Filesystem access is disabled")

        if not self.config.allow_delete:
            raise FileAccessDeniedError(str(path), "Delete operations are disabled")

        resolved_path = path.expanduser().resolve()

        # Check if directory is allowed
        is_allowed, reason = self._check_directory_write_access(resolved_path)
        if not is_allowed:
            raise FileAccessDeniedError(str(resolved_path), reason)

        if not resolved_path.exists():
            raise FileNotFoundError(f"Directory not found: {resolved_path}")

        if not resolved_path.is_dir():
            raise FileAccessDeniedError(
                str(resolved_path), "Path is not a directory"
            )

        # Delete directory
        try:
            if recursive:
                import shutil

                shutil.rmtree(resolved_path)
            else:
                resolved_path.rmdir()
            logger.info(f"Successfully deleted directory: {resolved_path}")
        except Exception as e:
            logger.error(f"Failed to delete directory {resolved_path}: {e}")
            raise

    def _check_write_access(self, path: Path) -> tuple[bool, str]:
        """Check if write access is allowed for a file path."""
        # Check if within allowed directories
        if self.config.allowed_directories:
            is_within_allowed = any(
                self._is_within_directory(path, allowed)
                for allowed in self.config.allowed_directories
            )
            if not is_within_allowed:
                return False, "Path is not within allowed directories"

        # Check blocked patterns
        path_lower = str(path).lower()
        for pattern in self.config.blocked_patterns:
            if pattern in path_lower:
                return False, f"Path matches blocked pattern: {pattern}"

        # Check allowed write extensions
        allowed_exts = (
            self.config.allowed_write_extensions or self.config.allowed_extensions
        )
        if allowed_exts is not None:
            ext = path.suffix.lower()
            if ext not in allowed_exts:
                return False, f"File extension {ext} not allowed for writing"

        # Check symlinks
        if not self.config.follow_symlinks and path.is_symlink():
            return False, "Symbolic links are not allowed"

        return True, "Write access allowed"

    def _check_directory_write_access(self, path: Path) -> tuple[bool, str]:
        """Check if directory creation is allowed."""
        # Check if within allowed directories
        if self.config.allowed_directories:
            is_within_allowed = any(
                self._is_within_directory(path, allowed)
                for allowed in self.config.allowed_directories
            )
            if not is_within_allowed:
                return False, "Path is not within allowed directories"

        # Check blocked patterns
        path_lower = str(path).lower()
        for pattern in self.config.blocked_patterns:
            if pattern in path_lower:
                return False, f"Path matches blocked pattern: {pattern}"

        return True, "Directory write access allowed"

    def _is_within_directory(self, path: Path, directory: Path) -> bool:
        """Check if path is within directory."""
        try:
            path.relative_to(directory)
            return True
        except ValueError:
            return False
