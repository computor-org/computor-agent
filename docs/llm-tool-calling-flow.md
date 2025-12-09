# LLM Tool Calling Flow

## Visual Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         Your Application                         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ 1. Get tool schemas
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      LLMFileSystemTools                          │
│                                                                  │
│  get_tool_schemas()  →  Returns list of available tools         │
│                         [read_file, write_file, search_code...] │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ 2. Pass to LLM
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        LLM (GPT-4/Claude/Ollama)                 │
│                                                                  │
│  User: "Review my main.py file"                                 │
│                                                                  │
│  LLM thinks: "I need to read the file first"                    │
│                                                                  │
│  LLM returns: tool_call(name="read_file", args={path: ...})     │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ 3. Execute tool
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      LLMFileSystemTools                          │
│                                                                  │
│  execute_tool("read_file", {path: "main.py"})                   │
│      │                                                           │
│      └──► RestrictedFileReader.read_file()                      │
│              │                                                   │
│              └──► Security checks (whitelist, patterns, size)   │
│                      │                                           │
│                      └──► Returns file content or error         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ 4. Return result
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        LLM (GPT-4/Claude/Ollama)                 │
│                                                                  │
│  Tool result: {success: true, content: "def main()..."}         │
│                                                                  │
│  LLM analyzes code and generates response                       │
│                                                                  │
│  LLM returns: "I reviewed your code. Here are my suggestions..."│
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ 5. Display to user
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                              User                                │
│                                                                  │
│  Sees: "I reviewed your code. Here are my suggestions..."       │
└─────────────────────────────────────────────────────────────────┘
```

## Step-by-Step Flow

### Step 1: Setup
```python
# Your application sets up filesystem tools
config = FileSystemAccessConfig(
    allowed_directories=[Path("/tmp/workspace")],
    allow_write=True,
)

tools = LLMFileSystemTools(config)
schemas = tools.get_tool_schemas()
```

### Step 2: User Request
```python
# User asks a question
user_message = "Can you review my main.py file?"
```

### Step 3: LLM Decides to Use Tool
```python
# Send to LLM with available tools
response = openai.ChatCompletion.create(
    model="gpt-4",
    messages=[{"role": "user", "content": user_message}],
    tools=schemas  # ← LLM now knows what tools are available
)

# LLM returns a tool call
# response.choices[0].message.tool_calls[0] = {
#     "function": {
#         "name": "read_file",
#         "arguments": '{"path": "/tmp/workspace/main.py"}'
#     }
# }
```

### Step 4: Execute Tool
```python
# Your application executes the tool call
tool_call = response.choices[0].message.tool_calls[0]

result = await tools.execute_tool(
    tool_name=tool_call.function.name,  # "read_file"
    arguments=json.loads(tool_call.function.arguments)  # {path: ...}
)

# Result: {
#     "success": true,
#     "path": "/tmp/workspace/main.py",
#     "content": "def main():\n    print('hello')\n...",
#     "size": 245
# }
```

### Step 5: Send Result Back to LLM
```python
# Add tool result to conversation
messages.append({
    "role": "tool",
    "tool_call_id": tool_call.id,
    "name": "read_file",
    "content": json.dumps(result)
})

# LLM processes the result and generates final response
final = openai.ChatCompletion.create(
    model="gpt-4",
    messages=messages,
    tools=schemas
)

# LLM: "I reviewed your main.py file. Here are my suggestions:
#       1. The code looks good overall
#       2. Consider adding error handling..."
```

## Multi-Tool Example

When LLM needs multiple tools:

```
User: "Find all Python files and check each one for errors"

┌─────────────────────────────────┐
│ LLM Call 1: find_files          │
│ Arguments: {pattern: "*.py"}    │
└─────────────────────────────────┘
              ↓
┌─────────────────────────────────┐
│ Result: [main.py, utils.py]     │
└─────────────────────────────────┘
              ↓
┌─────────────────────────────────┐
│ LLM Call 2: read_file           │
│ Arguments: {path: "main.py"}    │
└─────────────────────────────────┘
              ↓
┌─────────────────────────────────┐
│ Result: {content: "..."}        │
└─────────────────────────────────┘
              ↓
┌─────────────────────────────────┐
│ LLM Call 3: read_file           │
│ Arguments: {path: "utils.py"}   │
└─────────────────────────────────┘
              ↓
┌─────────────────────────────────┐
│ Result: {content: "..."}        │
└─────────────────────────────────┘
              ↓
┌─────────────────────────────────┐
│ LLM Final Response:             │
│ "I checked both files..."       │
└─────────────────────────────────┘
```

## Security Flow

Every tool call goes through security checks:

```
Tool Call: read_file(path="/tmp/workspace/main.py")
     ↓
┌─────────────────────────────────────────┐
│ 1. Check if filesystem is enabled      │
│    ✓ config.enabled = True              │
└─────────────────────────────────────────┘
     ↓
┌─────────────────────────────────────────┐
│ 2. Resolve path (prevent ../escapes)   │
│    /tmp/workspace/main.py → resolved    │
└─────────────────────────────────────────┘
     ↓
┌─────────────────────────────────────────┐
│ 3. Check whitelist                      │
│    ✓ Is within allowed_directories      │
└─────────────────────────────────────────┘
     ↓
┌─────────────────────────────────────────┐
│ 4. Check blocked patterns               │
│    ✓ Doesn't match .env, credentials    │
└─────────────────────────────────────────┘
     ↓
┌─────────────────────────────────────────┐
│ 5. Check extension (if configured)      │
│    ✓ .py is in allowed_extensions       │
└─────────────────────────────────────────┘
     ↓
┌─────────────────────────────────────────┐
│ 6. Check file size                      │
│    ✓ File size < max_file_size_bytes    │
└─────────────────────────────────────────┘
     ↓
┌─────────────────────────────────────────┐
│ 7. Read file and return                 │
│    Return {success: true, content: ...} │
└─────────────────────────────────────────┘
```

If any check fails:
```
Return {success: false, error: "Access denied: ..."}
```

## Code Implementation

Minimal working example:

```python
from computor_agent.filesystem import (
    FileSystemAccessConfig,
    LLMFileSystemTools,
)
from pathlib import Path
import openai
import json

# 1. Setup
config = FileSystemAccessConfig(
    allowed_directories=[Path("/tmp/workspace")]
)
tools = LLMFileSystemTools(config)
schemas = tools.get_tool_schemas()

# 2. Send to LLM
messages = [{"role": "user", "content": "Read main.py"}]
response = openai.ChatCompletion.create(
    model="gpt-4",
    messages=messages,
    tools=schemas
)

# 3. Execute tools
if response.choices[0].message.tool_calls:
    for tc in response.choices[0].message.tool_calls:
        # Execute
        result = await tools.execute_tool(
            tc.function.name,
            json.loads(tc.function.arguments)
        )

        # Add to conversation
        messages.append({
            "role": "tool",
            "tool_call_id": tc.id,
            "content": json.dumps(result)
        })

    # 4. Get final response
    final = openai.ChatCompletion.create(
        model="gpt-4",
        messages=messages,
        tools=schemas
    )
    print(final.choices[0].message.content)
```

## Summary

The AI uses filesystem functions through this flow:

1. **You define** what tools are available (`get_tool_schemas()`)
2. **LLM decides** which tools to call based on the task
3. **You execute** the tool calls securely (`execute_tool()`)
4. **You return** results to the LLM
5. **LLM generates** the final response using those results

The key is the **tool calling loop** that runs 1-5 iterations until the LLM has enough information to answer the user's question!
