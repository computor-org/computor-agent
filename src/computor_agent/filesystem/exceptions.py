"""
Exceptions for filesystem operations.
"""


class FileSystemError(Exception):
    """Base exception for filesystem operations."""

    pass


class FileAccessDeniedError(FileSystemError):
    """Raised when access to a file or directory is denied."""

    def __init__(self, path: str, reason: str = "Access denied"):
        self.path = path
        self.reason = reason
        super().__init__(f"{reason}: {path}")


class FileSizeLimitExceededError(FileSystemError):
    """Raised when a file exceeds the size limit."""

    def __init__(self, path: str, size: int, limit: int):
        self.path = path
        self.size = size
        self.limit = limit
        super().__init__(f"File too large ({size} bytes > {limit} bytes): {path}")


class InvalidPathError(FileSystemError):
    """Raised when a path is invalid or malformed."""

    def __init__(self, path: str, reason: str = "Invalid path"):
        self.path = path
        self.reason = reason
        super().__init__(f"{reason}: {path}")


class SearchError(FileSystemError):
    """Raised when a search operation fails."""

    pass
