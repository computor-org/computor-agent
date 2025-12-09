# How LLMs Use Filesystem Functions

This guide explains how to integrate the filesystem tools with LLMs so they can actually use them.

## Overview

LLMs access the filesystem through **function calling** (also called "tool use"). The process works like this:

```
1. You give the LLM a list of available tools (function schemas)
2. The LLM decides which tools to call based on the user's request
3. Your code executes the tool calls
4. You send the results back to the LLM
5. The LLM uses those results to generate its final response
```

## Method 1: OpenAI Function Calling (Recommended)

Modern LLMs (OpenAI, Anthropic Claude, etc.) support native function calling.

### Step 1: Get Tool Schemas

```python
from computor_agent.filesystem import (
    FileSystemAccessConfig,
    LLMFileSystemTools,
)
from pathlib import Path

# Configure filesystem access
config = FileSystemAccessConfig(
    allowed_directories=[Path("/tmp/student-repos")],
    allow_write=True,  # Enable if needed
)

# Create tools
tools = LLMFileSystemTools(config)

# Get OpenAI-compatible schemas
tool_schemas = tools.get_tool_schemas()

# This returns a list like:
# [
#   {
#     "type": "function",
#     "function": {
#       "name": "read_file",
#       "description": "Read the contents of a file...",
#       "parameters": {...}
#     }
#   },
#   ...
# ]
```

### Step 2: Send to LLM with Available Tools

```python
import openai

# Send request with available tools
response = openai.ChatCompletion.create(
    model="gpt-4",
    messages=[
        {
            "role": "system",
            "content": "You are a helpful coding tutor. You can read and analyze student code."
        },
        {
            "role": "user",
            "content": "Can you review the main.py file in my project?"
        }
    ],
    tools=tool_schemas,  # Pass the filesystem tools
)
```

### Step 3: Execute Tool Calls

```python
import json

message = response.choices[0].message

# Check if LLM wants to call tools
if message.tool_calls:
    # Execute each tool call
    for tool_call in message.tool_calls:
        # Parse the tool call
        tool_name = tool_call.function.name
        arguments = json.loads(tool_call.function.arguments)

        # Execute using our filesystem tools
        result = await tools.execute_tool(
            tool_name=tool_name,
            arguments=arguments
        )

        # Add result to conversation
        messages.append({
            "role": "tool",
            "tool_call_id": tool_call.id,
            "name": tool_name,
            "content": json.dumps(result)
        })

    # Get final response from LLM
    final_response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=messages,
        tools=tool_schemas,
    )

    print(final_response.choices[0].message.content)
```

## Method 2: For Ollama / Local Models

Local models may not support native function calling, but you can implement it with prompt engineering.

### Approach A: JSON Mode

```python
import ollama
import json

# Create a system prompt that describes available tools
system_prompt = f"""You are a helpful assistant with access to filesystem tools.

Available tools:
{json.dumps(tool_schemas, indent=2)}

When you need to use a tool, respond with JSON in this format:
{{
  "thought": "Why I need to use this tool",
  "tool": "tool_name",
  "arguments": {{"param": "value"}}
}}

When you have the information you need, respond normally.
"""

# Send request
response = ollama.chat(
    model="qwen2.5-coder:7b",
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "Read the main.py file"}
    ],
    format="json"  # Force JSON output
)

# Parse response
try:
    tool_request = json.loads(response.message.content)

    if "tool" in tool_request:
        # Execute the tool
        result = await tools.execute_tool(
            tool_name=tool_request["tool"],
            arguments=tool_request["arguments"]
        )

        # Send result back to LLM
        response = ollama.chat(
            model="qwen2.5-coder:7b",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "Read the main.py file"},
                {"role": "assistant", "content": json.dumps(tool_request)},
                {"role": "user", "content": f"Tool result: {json.dumps(result)}"}
            ]
        )

        print(response.message.content)
except json.JSONDecodeError:
    # LLM responded with text instead of tool call
    print(response.message.content)
```

### Approach B: Anthropic-Style Tool Use

For Claude or similar models:

```python
import anthropic

client = anthropic.Anthropic()

# Convert to Anthropic tool format
anthropic_tools = [
    {
        "name": schema["function"]["name"],
        "description": schema["function"]["description"],
        "input_schema": schema["function"]["parameters"]
    }
    for schema in tool_schemas
]

# Send with tools
response = client.messages.create(
    model="claude-3-5-sonnet-20241022",
    max_tokens=4096,
    tools=anthropic_tools,
    messages=[
        {
            "role": "user",
            "content": "Can you check if there's a main.py file and read it?"
        }
    ]
)

# Process tool use
for block in response.content:
    if block.type == "tool_use":
        # Execute the tool
        result = await tools.execute_tool(
            tool_name=block.name,
            arguments=block.input
        )

        # Continue conversation with tool result
        response = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=4096,
            tools=anthropic_tools,
            messages=[
                {"role": "user", "content": "Check if there's a main.py file"},
                {"role": "assistant", "content": response.content},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result)
                        }
                    ]
                }
            ]
        )
```

## Complete Example: Tool Calling Loop

Here's a complete example that handles multiple tool calls:

```python
import asyncio
import json
from pathlib import Path
from computor_agent.filesystem import (
    FileSystemAccessConfig,
    LLMFileSystemTools,
)


async def chat_with_filesystem_access(
    user_message: str,
    workspace_path: Path,
    max_iterations: int = 5
):
    """
    Chat with an LLM that has filesystem access.

    Args:
        user_message: The user's question/request
        workspace_path: Path to the workspace the LLM can access
        max_iterations: Maximum number of tool calling iterations

    Returns:
        Final LLM response
    """
    # Setup
    config = FileSystemAccessConfig(
        allowed_directories=[workspace_path],
        allow_write=True,
    )

    tools = LLMFileSystemTools(config)
    tool_schemas = tools.get_tool_schemas()

    # Initialize conversation
    messages = [
        {
            "role": "system",
            "content": (
                "You are a helpful coding tutor. You can read student code, "
                "search for patterns, and help debug issues. "
                f"You have access to files in: {workspace_path}"
            )
        },
        {
            "role": "user",
            "content": user_message
        }
    ]

    # Tool calling loop
    for iteration in range(max_iterations):
        # Call LLM
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=messages,
            tools=tool_schemas,
        )

        message = response.choices[0].message
        messages.append(message)

        # Check if LLM wants to use tools
        if not message.tool_calls:
            # No more tools to call, return final answer
            return message.content

        # Execute all tool calls
        for tool_call in message.tool_calls:
            tool_name = tool_call.function.name
            arguments = json.loads(tool_call.function.arguments)

            print(f"[Tool Call {iteration+1}] {tool_name}({arguments})")

            # Execute the tool
            result = await tools.execute_tool(
                tool_name=tool_name,
                arguments=arguments
            )

            print(f"[Tool Result] {result}")

            # Add result to conversation
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": tool_name,
                "content": json.dumps(result)
            })

    return "Maximum iterations reached"


# Usage
async def main():
    workspace = Path("/tmp/student-repos/project1")

    response = await chat_with_filesystem_access(
        user_message="Can you find all Python files and check if main.py exists?",
        workspace_path=workspace
    )

    print(f"\nFinal Response:\n{response}")


asyncio.run(main())
```

## Integration with Tutor Agent

Here's how to integrate with the existing TutorAgent:

```python
from computor_agent.tutor.agent import TutorAgent
from computor_agent.tutor.context import ConversationContext
from computor_agent.filesystem import LLMFileSystemTools
from computor_agent.settings import ComputorConfig


class TutorAgentWithFilesystem:
    """TutorAgent extended with filesystem access."""

    def __init__(self, config: ComputorConfig, tutor_agent: TutorAgent):
        self.config = config
        self.agent = tutor_agent

        # Create filesystem tools if enabled
        self.fs_tools = None
        if config.filesystem and config.filesystem.enabled:
            self.fs_tools = LLMFileSystemTools(config.filesystem)

    async def process_with_tools(
        self,
        user_message: str,
        context: ConversationContext,
    ) -> str:
        """Process a message with filesystem tool access."""

        if not self.fs_tools:
            # No filesystem access, use normal agent
            return await self.agent.process_message(...)

        # Get available tools
        tool_schemas = self.fs_tools.get_tool_schemas()

        # Build LLM messages
        messages = [
            {
                "role": "system",
                "content": self._build_system_prompt(context)
            },
            {
                "role": "user",
                "content": user_message
            }
        ]

        # Tool calling loop
        for _ in range(5):  # Max 5 iterations
            response = await self.agent.llm.complete(
                messages=messages,
                tools=tool_schemas,
            )

            if not response.tool_calls:
                return response.content

            # Execute tools
            for tool_call in response.tool_calls:
                result = await self.fs_tools.execute_tool(
                    tool_name=tool_call.name,
                    arguments=tool_call.arguments
                )

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result)
                })

        return "Processing complete"

    def _build_system_prompt(self, context: ConversationContext) -> str:
        """Build system prompt with context."""
        prompt = f"""You are a helpful coding tutor.

Student: {context.student.names[0] if context.student.names else 'Unknown'}
Assignment: {context.assignment.title if context.assignment else 'N/A'}

You can use filesystem tools to read and analyze their code.
"""
        return prompt
```

## Example: Multi-Step File Analysis

Here's what happens when an LLM uses multiple tools:

```python
# User asks: "Review my Python project and suggest improvements"

# Step 1: LLM calls find_files
tool_call = {
    "name": "find_files",
    "arguments": {
        "directory": "/tmp/student-repos/project1",
        "name_pattern": "*.py"
    }
}
# Result: ["main.py", "utils.py", "test_main.py"]

# Step 2: LLM calls read_file for main.py
tool_call = {
    "name": "read_file",
    "arguments": {
        "path": "/tmp/student-repos/project1/main.py"
    }
}
# Result: {file contents}

# Step 3: LLM calls search_code to find issues
tool_call = {
    "name": "search_code",
    "arguments": {
        "pattern": "TODO|FIXME",
        "directory": "/tmp/student-repos/project1"
    }
}
# Result: List of TODOs found

# Step 4: LLM generates final response
# "I reviewed your project. Here are my suggestions..."
```

## Security Considerations

### 1. Always Validate Tool Results

```python
result = await tools.execute_tool(tool_name, arguments)

if not result.get("success"):
    # Handle error
    error_message = result.get("error", "Unknown error")
    # Don't expose internal paths to LLM
    safe_error = "Access denied" if "denied" in error_message else "Error occurred"
```

### 2. Context-Aware Restrictions

```python
# Set allowed directories based on the student's context
config = FileSystemAccessConfig(
    allowed_directories=[
        context.student_code.repository_path,  # Only their repo
        # NOT the entire filesystem
    ],
    allow_write=False,  # Read-only for safety
)
```

### 3. Monitor Tool Usage

```python
# Log all tool calls
logger.info(f"LLM called {tool_name} with {arguments}")

# Set limits
if tool_call_count > 10:
    raise Exception("Too many tool calls, possible loop")
```

## Summary

The AI uses filesystem functions through **function calling**:

1. **You provide schemas** - `tools.get_tool_schemas()`
2. **LLM decides what to call** - Based on user request
3. **You execute the calls** - `tools.execute_tool(name, args)`
4. **You send results back** - LLM uses them to answer
5. **Repeat until done** - Usually 1-5 iterations

The key is the **tool calling loop** where you:
- Send available tools to LLM
- Execute any tool calls it makes
- Return results to LLM
- Let it continue until it has the answer

This works with OpenAI, Claude, Ollama, and any LLM that supports function calling!
