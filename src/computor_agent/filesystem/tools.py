"""
Unified LLM filesystem tools interface.

Provides a high-level interface for LLMs to interact with the filesystem
through function calling (OpenAI function calling format).
"""

import logging
from pathlib import Path
from typing import Any, Optional

from computor_agent.filesystem.config import FileSystemAccessConfig
from computor_agent.filesystem.exceptions import FileSystemError
from computor_agent.filesystem.reader import RestrictedFileReader
from computor_agent.filesystem.writer import RestrictedFileWriter
from computor_agent.filesystem.search import RestrictedSearchTools, SearchResult

logger = logging.getLogger(__name__)


class LLMFileSystemTools:
    """
    Unified filesystem interface for LLM function calling.

    Provides safe, restricted filesystem operations that can be exposed
    to LLMs through function calling APIs (OpenAI-compatible).

    Usage:
        config = FileSystemAccessConfig(
            allowed_directories=[Path("/tmp/repos")],
        )
        tools = LLMFileSystemTools(config)

        # Get tool schemas for LLM
        schemas = tools.get_tool_schemas()

        # Execute tool call
        result = await tools.execute_tool(
            tool_name="read_file",
            arguments={"path": "/tmp/repos/main.py"}
        )
    """

    def __init__(self, config: FileSystemAccessConfig):
        """
        Initialize LLM filesystem tools.

        Args:
            config: Filesystem access configuration
        """
        self.config = config
        self.reader = RestrictedFileReader(config)
        self.writer = RestrictedFileWriter(config)
        self.search = RestrictedSearchTools(config)

    def get_tool_schemas(self) -> list[dict[str, Any]]:
        """
        Get OpenAI function calling schemas for all available tools.

        Returns:
            List of tool schemas in OpenAI format
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Read the contents of a file from the student's repository. "
                    "Use this to examine code files, configuration files, or documentation.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "Path to the file to read (relative or absolute)",
                            },
                        },
                        "required": ["path"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "list_files",
                    "description": "List files in a directory. Use this to explore the repository structure.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "directory": {
                                "type": "string",
                                "description": "Directory path to list",
                            },
                            "recursive": {
                                "type": "boolean",
                                "description": "Whether to list files recursively (default: false)",
                            },
                        },
                        "required": ["directory"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "search_code",
                    "description": "Search for a pattern in code files using regular expressions. "
                    "Returns matching lines with line numbers.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "pattern": {
                                "type": "string",
                                "description": "Regular expression pattern to search for",
                            },
                            "directory": {
                                "type": "string",
                                "description": "Directory to search in",
                            },
                            "file_pattern": {
                                "type": "string",
                                "description": "File glob pattern (e.g., '*.py', '*.js'). Default: '*'",
                            },
                            "case_sensitive": {
                                "type": "boolean",
                                "description": "Whether search is case-sensitive (default: true)",
                            },
                        },
                        "required": ["pattern", "directory"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "find_files",
                    "description": "Find files by name pattern. Use this to locate specific files.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "directory": {
                                "type": "string",
                                "description": "Directory to search in",
                            },
                            "name_pattern": {
                                "type": "string",
                                "description": "Filename pattern (e.g., '*.py', 'test_*.js')",
                            },
                            "max_depth": {
                                "type": "integer",
                                "description": "Maximum depth to search (default: unlimited)",
                            },
                        },
                        "required": ["directory"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "check_file_access",
                    "description": "Check if a file can be accessed without reading it. "
                    "Returns whether access is allowed and the reason.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "File path to check",
                            },
                        },
                        "required": ["path"],
                    },
                },
            },
        ]

        # Add write tools if enabled
        if self.config.allow_write:
            schemas.extend([
                {
                    "type": "function",
                    "function": {
                        "name": "write_file",
                        "description": "Write content to a file. Creates the file if it doesn't exist, overwrites if it does.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "path": {
                                    "type": "string",
                                    "description": "Path to the file to write",
                                },
                                "content": {
                                    "type": "string",
                                    "description": "Content to write to the file",
                                },
                                "create_parents": {
                                    "type": "boolean",
                                    "description": "Create parent directories if they don't exist (default: true)",
                                },
                            },
                            "required": ["path", "content"],
                        },
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "append_file",
                        "description": "Append content to an existing file.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "path": {
                                    "type": "string",
                                    "description": "Path to the file to append to",
                                },
                                "content": {
                                    "type": "string",
                                    "description": "Content to append",
                                },
                            },
                            "required": ["path", "content"],
                        },
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "create_directory",
                        "description": "Create a new directory.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "path": {
                                    "type": "string",
                                    "description": "Path to the directory to create",
                                },
                                "parents": {
                                    "type": "boolean",
                                    "description": "Create parent directories if they don't exist (default: true)",
                                },
                            },
                            "required": ["path"],
                        },
                    },
                },
            ])

        # Add delete tools if enabled
        if self.config.allow_delete:
            schemas.extend([
                {
                    "type": "function",
                    "function": {
                        "name": "delete_file",
                        "description": "Delete a file.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "path": {
                                    "type": "string",
                                    "description": "Path to the file to delete",
                                },
                            },
                            "required": ["path"],
                        },
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "delete_directory",
                        "description": "Delete a directory.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "path": {
                                    "type": "string",
                                    "description": "Path to the directory to delete",
                                },
                                "recursive": {
                                    "type": "boolean",
                                    "description": "Delete directory and all contents (default: false)",
                                },
                            },
                            "required": ["path"],
                        },
                    },
                },
            ])

        return schemas

    async def execute_tool(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Execute a tool call from an LLM.

        Args:
            tool_name: Name of the tool to execute
            arguments: Tool arguments (from LLM function call)

        Returns:
            Tool execution result as a dict

        Raises:
            ValueError: If tool name is unknown
            FileSystemError: If tool execution fails
        """
        # Read operations
        if tool_name == "read_file":
            return await self._read_file(**arguments)
        elif tool_name == "list_files":
            return await self._list_files(**arguments)
        elif tool_name == "search_code":
            return await self._search_code(**arguments)
        elif tool_name == "find_files":
            return await self._find_files(**arguments)
        elif tool_name == "check_file_access":
            return await self._check_file_access(**arguments)
        # Write operations
        elif tool_name == "write_file":
            return await self._write_file(**arguments)
        elif tool_name == "append_file":
            return await self._append_file(**arguments)
        elif tool_name == "create_directory":
            return await self._create_directory(**arguments)
        # Delete operations
        elif tool_name == "delete_file":
            return await self._delete_file(**arguments)
        elif tool_name == "delete_directory":
            return await self._delete_directory(**arguments)
        else:
            raise ValueError(f"Unknown tool: {tool_name}")

    async def _read_file(self, path: str) -> dict[str, Any]:
        """Read file tool implementation."""
        try:
            content = self.reader.read_file(Path(path))
            return {
                "success": True,
                "path": path,
                "content": content,
                "size": len(content),
            }
        except FileSystemError as e:
            logger.warning(f"LLM read_file failed: {e}")
            return {
                "success": False,
                "path": path,
                "error": str(e),
                "error_type": type(e).__name__,
            }
        except Exception as e:
            logger.error(f"LLM read_file unexpected error: {e}")
            return {
                "success": False,
                "path": path,
                "error": f"Unexpected error: {e}",
                "error_type": "UnexpectedError",
            }

    async def _list_files(
        self, directory: str, recursive: bool = False
    ) -> dict[str, Any]:
        """List files tool implementation."""
        try:
            files = self.reader.list_directory(Path(directory), recursive=recursive)
            return {
                "success": True,
                "directory": directory,
                "files": [str(f) for f in files],
                "count": len(files),
            }
        except FileSystemError as e:
            logger.warning(f"LLM list_files failed: {e}")
            return {
                "success": False,
                "directory": directory,
                "error": str(e),
                "error_type": type(e).__name__,
            }
        except Exception as e:
            logger.error(f"LLM list_files unexpected error: {e}")
            return {
                "success": False,
                "directory": directory,
                "error": f"Unexpected error: {e}",
                "error_type": "UnexpectedError",
            }

    async def _search_code(
        self,
        pattern: str,
        directory: str,
        file_pattern: str = "*",
        case_sensitive: bool = True,
    ) -> dict[str, Any]:
        """Search code tool implementation."""
        try:
            # Use Python-based search for better cross-platform compatibility
            results = await self.search.grep_python(
                pattern=pattern,
                directory=Path(directory),
                case_sensitive=case_sensitive,
                recursive=True,
            )

            # Format results for LLM
            formatted_results = []
            for result in results:
                formatted_results.append(
                    {
                        "file": str(result.file_path),
                        "line": result.line_number,
                        "content": result.line_content,
                    }
                )

            return {
                "success": True,
                "pattern": pattern,
                "directory": directory,
                "matches": formatted_results,
                "count": len(formatted_results),
            }
        except FileSystemError as e:
            logger.warning(f"LLM search_code failed: {e}")
            return {
                "success": False,
                "pattern": pattern,
                "directory": directory,
                "error": str(e),
                "error_type": type(e).__name__,
            }
        except Exception as e:
            logger.error(f"LLM search_code unexpected error: {e}")
            return {
                "success": False,
                "pattern": pattern,
                "directory": directory,
                "error": f"Unexpected error: {e}",
                "error_type": "UnexpectedError",
            }

    async def _find_files(
        self,
        directory: str,
        name_pattern: Optional[str] = None,
        max_depth: Optional[int] = None,
    ) -> dict[str, Any]:
        """Find files tool implementation."""
        try:
            # Use Python-based find for better cross-platform compatibility
            files = self.search.find_python(
                directory=Path(directory),
                name_pattern=name_pattern,
                max_depth=max_depth,
            )

            return {
                "success": True,
                "directory": directory,
                "name_pattern": name_pattern,
                "files": [str(f) for f in files],
                "count": len(files),
            }
        except FileSystemError as e:
            logger.warning(f"LLM find_files failed: {e}")
            return {
                "success": False,
                "directory": directory,
                "error": str(e),
                "error_type": type(e).__name__,
            }
        except Exception as e:
            logger.error(f"LLM find_files unexpected error: {e}")
            return {
                "success": False,
                "directory": directory,
                "error": f"Unexpected error: {e}",
                "error_type": "UnexpectedError",
            }

    async def _check_file_access(self, path: str) -> dict[str, Any]:
        """Check file access tool implementation."""
        try:
            can_access, reason = self.reader.check_access(Path(path))
            return {
                "success": True,
                "path": path,
                "can_access": can_access,
                "reason": reason,
            }
        except Exception as e:
            logger.error(f"LLM check_file_access unexpected error: {e}")
            return {
                "success": False,
                "path": path,
                "error": f"Unexpected error: {e}",
                "error_type": "UnexpectedError",
            }

    async def _write_file(
        self, path: str, content: str, create_parents: bool = True
    ) -> dict[str, Any]:
        """Write file tool implementation."""
        try:
            self.writer.write_file(
                Path(path), content, create_parents=create_parents
            )
            return {
                "success": True,
                "path": path,
                "size": len(content),
                "message": "File written successfully",
            }
        except FileSystemError as e:
            logger.warning(f"LLM write_file failed: {e}")
            return {
                "success": False,
                "path": path,
                "error": str(e),
                "error_type": type(e).__name__,
            }
        except Exception as e:
            logger.error(f"LLM write_file unexpected error: {e}")
            return {
                "success": False,
                "path": path,
                "error": f"Unexpected error: {e}",
                "error_type": "UnexpectedError",
            }

    async def _append_file(self, path: str, content: str) -> dict[str, Any]:
        """Append file tool implementation."""
        try:
            self.writer.append_file(Path(path), content)
            return {
                "success": True,
                "path": path,
                "message": "Content appended successfully",
            }
        except FileSystemError as e:
            logger.warning(f"LLM append_file failed: {e}")
            return {
                "success": False,
                "path": path,
                "error": str(e),
                "error_type": type(e).__name__,
            }
        except Exception as e:
            logger.error(f"LLM append_file unexpected error: {e}")
            return {
                "success": False,
                "path": path,
                "error": f"Unexpected error: {e}",
                "error_type": "UnexpectedError",
            }

    async def _create_directory(
        self, path: str, parents: bool = True
    ) -> dict[str, Any]:
        """Create directory tool implementation."""
        try:
            self.writer.create_directory(Path(path), parents=parents)
            return {
                "success": True,
                "path": path,
                "message": "Directory created successfully",
            }
        except FileSystemError as e:
            logger.warning(f"LLM create_directory failed: {e}")
            return {
                "success": False,
                "path": path,
                "error": str(e),
                "error_type": type(e).__name__,
            }
        except Exception as e:
            logger.error(f"LLM create_directory unexpected error: {e}")
            return {
                "success": False,
                "path": path,
                "error": f"Unexpected error: {e}",
                "error_type": "UnexpectedError",
            }

    async def _delete_file(self, path: str) -> dict[str, Any]:
        """Delete file tool implementation."""
        try:
            self.writer.delete_file(Path(path))
            return {
                "success": True,
                "path": path,
                "message": "File deleted successfully",
            }
        except FileSystemError as e:
            logger.warning(f"LLM delete_file failed: {e}")
            return {
                "success": False,
                "path": path,
                "error": str(e),
                "error_type": type(e).__name__,
            }
        except Exception as e:
            logger.error(f"LLM delete_file unexpected error: {e}")
            return {
                "success": False,
                "path": path,
                "error": f"Unexpected error: {e}",
                "error_type": "UnexpectedError",
            }

    async def _delete_directory(
        self, path: str, recursive: bool = False
    ) -> dict[str, Any]:
        """Delete directory tool implementation."""
        try:
            self.writer.delete_directory(Path(path), recursive=recursive)
            return {
                "success": True,
                "path": path,
                "message": "Directory deleted successfully",
            }
        except FileSystemError as e:
            logger.warning(f"LLM delete_directory failed: {e}")
            return {
                "success": False,
                "path": path,
                "error": str(e),
                "error_type": type(e).__name__,
            }
        except Exception as e:
            logger.error(f"LLM delete_directory unexpected error: {e}")
            return {
                "success": False,
                "path": path,
                "error": f"Unexpected error: {e}",
                "error_type": "UnexpectedError",
            }

    def get_summary(self) -> dict[str, Any]:
        """
        Get a summary of the filesystem access configuration.

        Returns:
            Dict with configuration summary
        """
        return {
            "enabled": self.config.enabled,
            "allowed_directories": [str(d) for d in self.config.allowed_directories],
            "max_file_size_mb": self.config.max_file_size_bytes / (1024 * 1024),
            "allowed_extensions": self.config.allowed_extensions,
            "max_search_results": self.config.max_search_results,
            "search_timeout_seconds": self.config.search_timeout_seconds,
            "allow_write": self.config.allow_write,
            "allow_delete": self.config.allow_delete,
            "max_write_size_mb": self.config.max_write_size_bytes / (1024 * 1024) if self.config.allow_write else 0,
        }
