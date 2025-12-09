"""
Example: Integrating LLM Filesystem Tools with TutorAgent

This example demonstrates how to integrate the restricted filesystem
interface with the Tutor AI Agent, allowing LLMs to safely read files
and search code within whitelisted directories.
"""

import asyncio
from pathlib import Path
from typing import Any

from computor_agent.tutor.agent import TutorAgent
from computor_agent.tutor.config import TutorConfig
from computor_agent.tutor.context import ConversationContext
from computor_agent.filesystem import (
    FileSystemAccessConfig,
    LLMFileSystemTools,
)


class LLMWithFileSystem:
    """
    Example LLM client wrapper that supports filesystem operations.

    This wraps your existing LLM client and adds filesystem tool support.
    """

    def __init__(self, llm_client, filesystem_tools: LLMFileSystemTools):
        self.llm = llm_client
        self.fs_tools = filesystem_tools

    async def complete_with_tools(
        self,
        prompt: str,
        context: ConversationContext,
        max_iterations: int = 5,
    ) -> str:
        """
        Complete a prompt with filesystem tool support.

        The LLM can call filesystem tools to read files, search code, etc.
        This implements a simple tool calling loop.

        Args:
            prompt: The prompt for the LLM
            context: Conversation context (for security checks)
            max_iterations: Maximum tool calling iterations

        Returns:
            Final LLM response
        """
        messages = [{"role": "user", "content": prompt}]

        for iteration in range(max_iterations):
            # Call LLM with available tools
            response = await self.llm.complete(
                messages=messages,
                tools=self.fs_tools.get_tool_schemas(),
            )

            # Check if LLM wants to call a tool
            if hasattr(response, "tool_calls") and response.tool_calls:
                for tool_call in response.tool_calls:
                    # Execute the tool
                    result = await self.fs_tools.execute_tool(
                        tool_name=tool_call.name,
                        arguments=tool_call.arguments,
                    )

                    # Add tool result to messages
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": str(result),
                        }
                    )

                # Continue the loop to get next LLM response
                continue
            else:
                # No more tool calls, return final response
                return response.content

        return "Maximum iterations reached"


async def example_basic_usage():
    """Example: Basic filesystem tool usage."""
    print("=== Example 1: Basic Usage ===\n")

    # Configure filesystem access
    config = FileSystemAccessConfig(
        enabled=True,
        allowed_directories=[Path("/tmp/student-repos")],
        max_file_size_bytes=1_000_000,
        allowed_extensions=[".py", ".js", ".txt", ".md"],
    )

    tools = LLMFileSystemTools(config)

    # Read a file
    result = await tools.execute_tool(
        tool_name="read_file",
        arguments={"path": "/tmp/student-repos/main.py"},
    )

    if result["success"]:
        print(f"✓ Read file: {result['path']}")
        print(f"  Size: {result['size']} bytes")
        print(f"  Content preview: {result['content'][:100]}...")
    else:
        print(f"✗ Error: {result['error']}")

    print()


async def example_search_code():
    """Example: Search for patterns in code."""
    print("=== Example 2: Search Code ===\n")

    config = FileSystemAccessConfig(
        allowed_directories=[Path("/tmp/student-repos")],
    )

    tools = LLMFileSystemTools(config)

    # Search for function definitions
    result = await tools.execute_tool(
        tool_name="search_code",
        arguments={
            "pattern": r"def \w+\(",
            "directory": "/tmp/student-repos",
            "file_pattern": "*.py",
            "case_sensitive": True,
        },
    )

    if result["success"]:
        print(f"✓ Found {result['count']} matches")
        for match in result["matches"][:5]:  # Show first 5
            print(f"  {match['file']}:{match['line']}: {match['content']}")
    else:
        print(f"✗ Error: {result['error']}")

    print()


async def example_tutor_agent_integration():
    """Example: Full integration with TutorAgent."""
    print("=== Example 3: TutorAgent Integration ===\n")

    # Load tutor configuration with filesystem settings
    config = TutorConfig(
        filesystem=FileSystemAccessConfig(
            enabled=True,
            allowed_directories=[
                Path("/tmp/student-repos"),
                Path("/opt/reference-solutions"),
            ],
            max_file_size_bytes=10_000_000,
            allowed_extensions=[".py", ".js", ".java", ".txt", ".md"],
            blocked_patterns=[".env", "credentials", ".ssh"],
        )
    )

    # Create filesystem tools
    fs_tools = LLMFileSystemTools(config.filesystem)

    # Get tool schemas for LLM
    schemas = fs_tools.get_tool_schemas()
    print(f"✓ Loaded {len(schemas)} filesystem tools:")
    for schema in schemas:
        print(f"  - {schema['function']['name']}")

    print()


async def example_with_security_checks():
    """Example: Using SecurityGate with filesystem access."""
    print("=== Example 4: With Security Checks ===\n")

    from computor_agent.tutor.security import SecurityGate

    # Mock context (in real usage, this comes from ContextBuilder)
    class MockContext:
        student_code = type(
            "obj", (object,), {"repository_path": Path("/tmp/student-repos")}
        )()

    context = MockContext()

    # Create security gate
    # Note: In production, pass proper config and LLM client
    config = FileSystemAccessConfig(
        allowed_directories=[Path("/tmp/student-repos")],
    )

    # Check if LLM can access a file
    security_gate = type("obj", (object,), {})()  # Mock for example

    # In production:
    # is_allowed, reason = security_gate.check_file_access(
    #     requested_path=Path("/tmp/student-repos/main.py"),
    #     context=context,
    # )

    print("✓ Security checks would validate:")
    print("  - Path is within repository boundaries")
    print("  - Path doesn't match sensitive patterns")
    print("  - Path passes all security rules")

    print()


async def example_error_handling():
    """Example: Proper error handling."""
    print("=== Example 5: Error Handling ===\n")

    config = FileSystemAccessConfig(
        allowed_directories=[Path("/tmp/student-repos")],
        max_file_size_bytes=1000,  # Very small limit for demo
    )

    tools = LLMFileSystemTools(config)

    # Try to read a file outside allowed directories
    result = await tools.execute_tool(
        tool_name="read_file",
        arguments={"path": "/etc/passwd"},
    )

    print(f"Read /etc/passwd: {result['success']}")
    if not result["success"]:
        print(f"  Error: {result['error']}")
        print(f"  Type: {result['error_type']}")

    print()


async def example_openai_function_calling():
    """Example: OpenAI-style function calling format."""
    print("=== Example 6: OpenAI Function Calling ===\n")

    config = FileSystemAccessConfig(
        allowed_directories=[Path("/tmp/student-repos")],
    )

    tools = LLMFileSystemTools(config)

    # Get schemas in OpenAI format
    schemas = tools.get_tool_schemas()

    print("OpenAI function schema example:")
    print("```python")
    print("response = openai.ChatCompletion.create(")
    print("    model='gpt-4',")
    print("    messages=[{'role': 'user', 'content': 'Read main.py'}],")
    print("    tools=schemas,  # Pass our filesystem tools")
    print(")")
    print()
    print("# When LLM calls a tool:")
    print("tool_call = response.choices[0].message.tool_calls[0]")
    print("result = await tools.execute_tool(")
    print("    tool_name=tool_call.function.name,")
    print("    arguments=json.loads(tool_call.function.arguments),")
    print(")")
    print("```")

    print()


async def example_configuration_summary():
    """Example: View configuration summary."""
    print("=== Example 7: Configuration Summary ===\n")

    config = FileSystemAccessConfig(
        enabled=True,
        allowed_directories=[
            Path("/tmp/student-repos"),
            Path("/opt/reference-solutions"),
        ],
        max_file_size_bytes=10_000_000,
        allowed_extensions=[".py", ".js", ".txt"],
        max_search_results=50,
        search_timeout_seconds=20.0,
    )

    tools = LLMFileSystemTools(config)
    summary = tools.get_summary()

    print("Filesystem Configuration:")
    print(f"  Enabled: {summary['enabled']}")
    print(f"  Allowed directories: {len(summary['allowed_directories'])}")
    for dir in summary["allowed_directories"]:
        print(f"    - {dir}")
    print(f"  Max file size: {summary['max_file_size_mb']:.1f} MB")
    print(f"  Allowed extensions: {summary['allowed_extensions']}")
    print(f"  Max search results: {summary['max_search_results']}")
    print(f"  Search timeout: {summary['search_timeout_seconds']}s")

    print()


async def main():
    """Run all examples."""
    print("=" * 60)
    print("LLM Filesystem Integration Examples")
    print("=" * 60)
    print()

    try:
        await example_basic_usage()
    except Exception as e:
        print(f"Example 1 error: {e}\n")

    try:
        await example_search_code()
    except Exception as e:
        print(f"Example 2 error: {e}\n")

    try:
        await example_tutor_agent_integration()
    except Exception as e:
        print(f"Example 3 error: {e}\n")

    try:
        await example_with_security_checks()
    except Exception as e:
        print(f"Example 4 error: {e}\n")

    try:
        await example_error_handling()
    except Exception as e:
        print(f"Example 5 error: {e}\n")

    try:
        await example_openai_function_calling()
    except Exception as e:
        print(f"Example 6 error: {e}\n")

    try:
        await example_configuration_summary()
    except Exception as e:
        print(f"Example 7 error: {e}\n")

    print("=" * 60)
    print("Examples completed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
