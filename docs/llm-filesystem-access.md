# LLM Filesystem Access

This document explains the restricted filesystem interface that allows LLMs to safely read files and search code within whitelisted directories.

## Overview

The filesystem access system provides secure, sandboxed file operations for LLMs with:

- **Whitelist-based access** - Only specific directories are accessible
- **Extension filtering** - Restrict file types that can be read
- **Pattern blocking** - Prevent access to sensitive files (credentials, keys)
- **Size limits** - Prevent reading large files
- **Path traversal protection** - Prevent escaping allowed directories via `../`
- **Search tools** - Safe grep/find operations with result limits

## Architecture

```
LLMFileSystemTools (Unified Interface)
├── RestrictedFileReader (File reading)
└── RestrictedSearchTools (grep/find operations)
    └── FileSystemAccessConfig (Configuration)
```

## Configuration

### Basic Setup

Add to your `config.yaml`:

```yaml
# Agent-wide settings:
filesystem:
    enabled: true
    allowed_directories:
      - /tmp/student-repos
      - /opt/reference-solutions
    max_file_size_bytes: 10000000  # 10 MB
    allowed_extensions: [".py", ".js", ".java", ".txt", ".md"]
    blocked_patterns: [".env", "credentials", ".ssh", "token"]
    max_search_results: 100
    search_timeout_seconds: 30.0
    follow_symlinks: false  # Security: don't follow symlinks
```

### Configuration Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enabled` | bool | `true` | Enable filesystem access |
| `allowed_directories` | list[Path] | `[]` | Whitelisted directories (absolute paths) |
| `max_file_size_bytes` | int | `10_000_000` | Max file size (10 MB) |
| `allowed_extensions` | list[str] | `None` | Allowed file extensions (`None` = all) |
| `blocked_patterns` | list[str] | See below | Filename patterns to block |
| `max_search_results` | int | `100` | Max search results to return |
| `search_timeout_seconds` | float | `30.0` | Timeout for search operations |
| `follow_symlinks` | bool | `false` | Allow following symbolic links |

### Default Blocked Patterns

The following patterns are blocked by default (case-insensitive):

- `.env` - Environment variables
- `credentials` - Credential files
- `secrets` - Secret files
- `.ssh` - SSH keys
- `.git/config` - Git configuration
- `id_rsa`, `id_ed25519` - SSH private keys
- `.password` - Password files
- `token` - Token files
- `.key` - Key files
- `private` - Private files

## Usage

### 1. RestrictedFileReader

Read files with security checks:

```python
from pathlib import Path
from computor_agent.filesystem import (
    FileSystemAccessConfig,
    RestrictedFileReader,
)

# Configure
config = FileSystemAccessConfig(
    allowed_directories=[Path("/tmp/repos")],
    max_file_size_bytes=1_000_000,
)

reader = RestrictedFileReader(config)

# Read a file
try:
    content = reader.read_file(Path("/tmp/repos/main.py"))
    print(content)
except FileAccessDeniedError as e:
    print(f"Access denied: {e}")
except FileSizeLimitExceededError as e:
    print(f"File too large: {e}")

# Safe read (returns None on error)
content = reader.read_file_safe(Path("/tmp/repos/main.py"))

# Read multiple files
files = reader.read_files([
    Path("/tmp/repos/main.py"),
    Path("/tmp/repos/utils.py"),
])

# List directory
files = reader.list_directory(Path("/tmp/repos"), recursive=True)

# Check access without reading
can_access, reason = reader.check_access(Path("/tmp/repos/main.py"))
```

### 2. RestrictedSearchTools

Search code with security checks:

```python
from pathlib import Path
from computor_agent.filesystem import (
    FileSystemAccessConfig,
    RestrictedSearchTools,
)

config = FileSystemAccessConfig(
    allowed_directories=[Path("/tmp/repos")],
)

search = RestrictedSearchTools(config)

# Python-based grep (cross-platform)
results = await search.grep_python(
    pattern=r"def \w+\(",
    directory=Path("/tmp/repos"),
    case_sensitive=True,
    recursive=True,
)

for result in results:
    print(f"{result.file_path}:{result.line_number}: {result.line_content}")

# Python-based find
files = search.find_python(
    directory=Path("/tmp/repos"),
    name_pattern="*.py",
    max_depth=3,
)
```

### 3. LLMFileSystemTools (OpenAI Function Calling)

Unified interface for LLM function calling:

```python
from computor_agent.filesystem import (
    FileSystemAccessConfig,
    LLMFileSystemTools,
)

config = FileSystemAccessConfig(
    allowed_directories=[Path("/tmp/repos")],
)

tools = LLMFileSystemTools(config)

# Get OpenAI function schemas
schemas = tools.get_tool_schemas()
# Pass to LLM with function calling support

# Execute tool calls from LLM
result = await tools.execute_tool(
    tool_name="read_file",
    arguments={"path": "/tmp/repos/main.py"}
)

if result["success"]:
    print(result["content"])
else:
    print(f"Error: {result['error']}")
```

## Available Tools for LLMs

### read_file

Read the contents of a file.

**Arguments:**
- `path` (string): Path to the file to read

**Returns:**
```json
{
  "success": true,
  "path": "/tmp/repos/main.py",
  "content": "print('hello')",
  "size": 15
}
```

### list_files

List files in a directory.

**Arguments:**
- `directory` (string): Directory path to list
- `recursive` (boolean, optional): List recursively

**Returns:**
```json
{
  "success": true,
  "directory": "/tmp/repos",
  "files": ["main.py", "utils.py"],
  "count": 2
}
```

### search_code

Search for a pattern in code files.

**Arguments:**
- `pattern` (string): Regular expression pattern
- `directory` (string): Directory to search in
- `file_pattern` (string, optional): File glob pattern (e.g., "*.py")
- `case_sensitive` (boolean, optional): Case sensitivity

**Returns:**
```json
{
  "success": true,
  "pattern": "def",
  "directory": "/tmp/repos",
  "matches": [
    {
      "file": "/tmp/repos/main.py",
      "line": 5,
      "content": "def hello():"
    }
  ],
  "count": 1
}
```

### find_files

Find files by name pattern.

**Arguments:**
- `directory` (string): Directory to search in
- `name_pattern` (string, optional): Filename pattern (e.g., "*.py")
- `max_depth` (integer, optional): Maximum depth

**Returns:**
```json
{
  "success": true,
  "directory": "/tmp/repos",
  "name_pattern": "*.py",
  "files": ["main.py", "utils.py"],
  "count": 2
}
```

### check_file_access

Check if a file can be accessed.

**Arguments:**
- `path` (string): File path to check

**Returns:**
```json
{
  "success": true,
  "path": "/tmp/repos/main.py",
  "can_access": true,
  "reason": "Access allowed"
}
```

## Security Features

### 1. Path Whitelisting

Only files within `allowed_directories` can be accessed:

```python
# ✓ Allowed
/tmp/student-repos/project1/main.py

# ✗ Denied (outside allowed directories)
/etc/passwd
/home/user/.ssh/id_rsa
```

### 2. Path Traversal Protection

All paths are resolved to absolute paths to prevent escaping:

```python
# ✗ Denied (tries to escape)
/tmp/student-repos/../../../etc/passwd  # Resolves to /etc/passwd
```

### 3. Pattern Blocking

Files matching blocked patterns are always denied:

```python
# ✗ Denied (matches blocked pattern)
/tmp/student-repos/.env
/tmp/student-repos/credentials.json
/tmp/student-repos/.ssh/id_rsa
```

### 4. Extension Filtering

Only allowed file extensions can be read (if configured):

```python
config = FileSystemAccessConfig(
    allowed_extensions=[".py", ".js", ".txt"]
)

# ✓ Allowed
main.py
script.js
notes.txt

# ✗ Denied
malware.exe
binary.so
```

### 5. Size Limits

Large files are rejected to prevent resource exhaustion:

```python
# ✗ Denied if file > max_file_size_bytes
huge_file.txt  # 50 MB
```

### 6. Symlink Protection

By default, symbolic links are not followed to prevent escaping allowed directories:

```python
# ✗ Denied (symlink pointing outside)
/tmp/student-repos/link -> /etc/passwd
```

## Integration with SecurityGate

The `SecurityGate` class provides additional validation for LLM file access requests:

```python
from computor_agent.tutor.security import SecurityGate

# Check if LLM can access a file
is_allowed, reason = security_gate.check_file_access(
    requested_path=Path("/tmp/repos/main.py"),
    context=conversation_context,
)

if not is_allowed:
    print(f"Access denied: {reason}")

# Validate search directory
is_allowed, reason = security_gate.validate_search_directory(
    directory=Path("/tmp/repos"),
    context=conversation_context,
)
```

The SecurityGate ensures:
- Path is within repository boundaries from context
- Path doesn't match sensitive file patterns
- Path passes all security checks

## Example: Full Integration

```python
import asyncio
from pathlib import Path
from computor_agent.filesystem import (
    FileSystemAccessConfig,
    LLMFileSystemTools,
)
from computor_agent.tutor.security import SecurityGate
from computor_agent.tutor.context import ConversationContext

async def process_llm_tool_call(
    tool_name: str,
    arguments: dict,
    context: ConversationContext,
    security_gate: SecurityGate,
):
    """Process an LLM tool call with security checks."""

    # Configure filesystem access
    config = FileSystemAccessConfig(
        allowed_directories=[
            context.student_code.repository_path,
        ],
        max_file_size_bytes=1_000_000,
        allowed_extensions=[".py", ".js", ".txt", ".md"],
    )

    tools = LLMFileSystemTools(config)

    # Additional security check for file access
    if tool_name == "read_file":
        requested_path = Path(arguments["path"])
        is_allowed, reason = security_gate.check_file_access(
            requested_path=requested_path,
            context=context,
        )
        if not is_allowed:
            return {
                "success": False,
                "error": f"Security check failed: {reason}",
            }

    # Execute tool
    result = await tools.execute_tool(tool_name, arguments)
    return result

# Usage
result = await process_llm_tool_call(
    tool_name="read_file",
    arguments={"path": "/tmp/repos/main.py"},
    context=context,
    security_gate=security_gate,
)
```

## Testing

Run the filesystem tests:

```bash
pytest tests/test_filesystem.py -v
```

## Best Practices

1. **Always use whitelisting** - Never rely on blacklisting alone
2. **Set size limits** - Prevent resource exhaustion
3. **Disable symlinks** - Unless you have a specific need
4. **Use SecurityGate** - Add an additional security layer
5. **Log access attempts** - Monitor for suspicious activity
6. **Regular audits** - Review allowed directories and patterns
7. **Principle of least privilege** - Only allow what's necessary

## Troubleshooting

### Access Denied Error

```
FileAccessDeniedError: Path is not within allowed directories
```

**Solution:** Verify the file is within an allowed directory in `allowed_directories`.

### File Too Large Error

```
FileSizeLimitExceededError: File too large (15000000 bytes > 10000000 bytes)
```

**Solution:** Increase `max_file_size_bytes` or use a smaller file.

### Extension Not Allowed

```
FileAccessDeniedError: File extension .exe not allowed
```

**Solution:** Add the extension to `allowed_extensions` or remove the restriction.

### Pattern Blocked

```
FileAccessDeniedError: Path matches blocked pattern: .env
```

**Solution:** Rename the file or remove the pattern from `blocked_patterns`.

## Future Enhancements

- [ ] Rate limiting per LLM session
- [ ] Content filtering (prevent reading binary files)
- [ ] Audit logging with rotation
- [ ] Directory size limits
- [ ] File type detection (magic numbers)
- [ ] Sandboxed execution for code search
- [ ] Cache frequently accessed files
- [ ] Support for remote filesystems (S3, etc.)
