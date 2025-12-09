"""
Restricted filesystem interface for LLM access.

This module provides secure, sandboxed filesystem access for LLMs,
including file reading and search operations with strict whitelisting
and validation.
"""

from computor_agent.filesystem.config import FileSystemAccessConfig
from computor_agent.filesystem.exceptions import (
    FileAccessDeniedError,
    FileSizeLimitExceededError,
    FileSystemError,
    InvalidPathError,
    SearchError,
)
from computor_agent.filesystem.reader import RestrictedFileReader
from computor_agent.filesystem.writer import RestrictedFileWriter
from computor_agent.filesystem.search import RestrictedSearchTools
from computor_agent.filesystem.tools import LLMFileSystemTools

__all__ = [
    "FileSystemAccessConfig",
    "FileAccessDeniedError",
    "FileSizeLimitExceededError",
    "FileSystemError",
    "InvalidPathError",
    "SearchError",
    "RestrictedFileReader",
    "RestrictedFileWriter",
    "RestrictedSearchTools",
    "LLMFileSystemTools",
]
