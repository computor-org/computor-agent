"""
Example: Using Filesystem Tools with Ollama (Local LLM)

This example shows how to integrate filesystem tools with Ollama,
which doesn't have native function calling support. We use prompt
engineering to enable tool use.
"""

import asyncio
import json
from pathlib import Path
from typing import Optional

from computor_agent.filesystem import (
    FileSystemAccessConfig,
    LLMFileSystemTools,
)


class OllamaWithTools:
    """
    Wrapper for Ollama that adds tool calling capability.

    Uses prompt engineering to make Ollama use tools.
    """

    def __init__(self, model: str = "qwen2.5-coder:7b"):
        self.model = model
        self.tools = None
        self.tool_schemas = []

    def set_tools(self, tools: LLMFileSystemTools):
        """Set available filesystem tools."""
        self.tools = tools
        self.tool_schemas = tools.get_tool_schemas()

    def _build_system_prompt(self) -> str:
        """Build system prompt that teaches the LLM about tools."""
        if not self.tool_schemas:
            return "You are a helpful assistant."

        tools_description = "Available tools:\n\n"
        for schema in self.tool_schemas:
            func = schema["function"]
            tools_description += f"### {func['name']}\n"
            tools_description += f"{func['description']}\n"
            tools_description += f"Parameters: {json.dumps(func['parameters'], indent=2)}\n\n"

        return f"""You are a helpful coding tutor with access to filesystem tools.

{tools_description}

To use a tool, respond with JSON in this exact format:
{{
  "tool": "tool_name",
  "arguments": {{"param": "value"}},
  "thought": "Why you're using this tool"
}}

After you receive tool results, analyze them and provide a helpful response to the user.

When you're ready to give a final answer (no more tools needed), respond with regular text.
"""

    async def chat(self, message: str, workspace: Path) -> str:
        """
        Chat with Ollama using filesystem tools.

        Args:
            message: User's message
            workspace: Workspace path for filesystem access

        Returns:
            Final response from LLM
        """
        import httpx

        system_prompt = self._build_system_prompt()
        messages = [message]
        tool_results = []

        # Tool calling loop (max 5 iterations)
        for iteration in range(5):
            # Build prompt
            prompt = f"{system_prompt}\n\n"

            if tool_results:
                prompt += "Previous tool results:\n"
                for result in tool_results:
                    prompt += f"{json.dumps(result, indent=2)}\n\n"

            prompt += f"User: {message}\n\n"
            prompt += "Assistant (respond with tool JSON or final answer):"

            # Call Ollama
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "http://localhost:11434/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False,
                    },
                    timeout=60.0,
                )
                result = response.json()
                llm_response = result["response"].strip()

            print(f"\n[Iteration {iteration + 1}] LLM Response:")
            print(llm_response[:200] + "..." if len(llm_response) > 200 else llm_response)

            # Try to parse as tool call
            try:
                # Extract JSON from response
                tool_call = self._extract_json(llm_response)

                if tool_call and "tool" in tool_call:
                    # Execute tool
                    print(f"\n[Tool Call] {tool_call['tool']}({tool_call['arguments']})")

                    tool_result = await self.tools.execute_tool(
                        tool_name=tool_call["tool"],
                        arguments=tool_call["arguments"]
                    )

                    print(f"[Tool Result] Success: {tool_result.get('success')}")

                    tool_results.append({
                        "tool": tool_call["tool"],
                        "arguments": tool_call["arguments"],
                        "result": tool_result
                    })

                    # Continue loop to let LLM process result
                    continue
                else:
                    # No tool call, this is the final answer
                    return llm_response

            except (json.JSONDecodeError, KeyError):
                # Response is not JSON, treat as final answer
                return llm_response

        return "Maximum iterations reached"

    def _extract_json(self, text: str) -> Optional[dict]:
        """Extract JSON from text that may contain other content."""
        # Try to find JSON object in the text
        start = text.find("{")
        end = text.rfind("}") + 1

        if start == -1 or end == 0:
            return None

        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            return None


async def example_code_review():
    """Example: Ask LLM to review code in a directory."""
    print("=" * 60)
    print("Example: Code Review with Filesystem Access")
    print("=" * 60)

    # Setup workspace (create some example files)
    workspace = Path("/tmp/example-project")
    workspace.mkdir(exist_ok=True)

    (workspace / "main.py").write_text("""
def calculate_sum(a, b):
    result = a + b
    return result

def main():
    x = 5
    y = 10
    total = calculate_sum(x, y)
    print(f"The sum is: {total}")

if __name__ == "__main__":
    main()
""")

    (workspace / "utils.py").write_text("""
def helper_function():
    # TODO: Implement this
    pass
""")

    # Configure filesystem access
    config = FileSystemAccessConfig(
        allowed_directories=[workspace],
        allow_write=False,  # Read-only for code review
    )

    # Create tools
    tools = LLMFileSystemTools(config)

    # Create Ollama client with tools
    ollama = OllamaWithTools(model="qwen2.5-coder:7b")
    ollama.set_tools(tools)

    # Ask for code review
    response = await ollama.chat(
        message="Can you review the Python files in this project and suggest improvements?",
        workspace=workspace
    )

    print("\n" + "=" * 60)
    print("Final Response:")
    print("=" * 60)
    print(response)


async def example_find_and_fix():
    """Example: Ask LLM to find TODOs and create a summary file."""
    print("\n" + "=" * 60)
    print("Example: Find TODOs and Write Summary")
    print("=" * 60)

    workspace = Path("/tmp/example-project")

    # Configure with write access
    config = FileSystemAccessConfig(
        allowed_directories=[workspace],
        allow_write=True,  # Enable writing
        allowed_write_extensions=[".txt", ".md"],
    )

    tools = LLMFileSystemTools(config)

    ollama = OllamaWithTools()
    ollama.set_tools(tools)

    # Ask to find TODOs and create summary
    response = await ollama.chat(
        message="Search for TODO comments in all Python files, then write a summary to todos.txt",
        workspace=workspace
    )

    print("\n" + "=" * 60)
    print("Final Response:")
    print("=" * 60)
    print(response)

    # Check if file was created
    todo_file = workspace / "todos.txt"
    if todo_file.exists():
        print("\n✓ todos.txt was created:")
        print(todo_file.read_text())


async def example_interactive():
    """Interactive example: Chat with filesystem access."""
    print("\n" + "=" * 60)
    print("Interactive Chat with Filesystem Access")
    print("=" * 60)

    workspace = Path("/tmp/example-project")

    config = FileSystemAccessConfig(
        allowed_directories=[workspace],
        allow_write=True,
    )

    tools = LLMFileSystemTools(config)
    ollama = OllamaWithTools()
    ollama.set_tools(tools)

    print(f"\nWorkspace: {workspace}")
    print("Available tools:", len(tools.get_tool_schemas()))
    print("\nType 'quit' to exit")

    while True:
        try:
            user_input = input("\nYou: ").strip()

            if user_input.lower() in ["quit", "exit", "q"]:
                break

            if not user_input:
                continue

            response = await ollama.chat(
                message=user_input,
                workspace=workspace
            )

            print(f"\nAssistant: {response}")

        except KeyboardInterrupt:
            print("\n\nExiting...")
            break
        except Exception as e:
            print(f"\nError: {e}")


async def main():
    """Run all examples."""
    print("LLM Filesystem Integration Examples")
    print("=" * 60)
    print("\nThese examples use Ollama with qwen2.5-coder:7b")
    print("Make sure Ollama is running: ollama serve")
    print("And the model is installed: ollama pull qwen2.5-coder:7b")
    print("\n")

    try:
        # Example 1: Code review
        await example_code_review()

        # Example 2: Find and fix
        await example_find_and_fix()

        # Example 3: Interactive (commented out by default)
        # await example_interactive()

    except Exception as e:
        print(f"\nError running examples: {e}")
        print("\nMake sure Ollama is running and qwen2.5-coder:7b is installed")


if __name__ == "__main__":
    asyncio.run(main())
