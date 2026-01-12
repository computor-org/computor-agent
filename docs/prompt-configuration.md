# Prompt Configuration System

## Overview

The tutor agent now supports **fully configurable prompts** loaded from markdown files, with automatic initialization and hot reload in development mode.

## Features

### 1. Custom Prompts Directory

You can specify where prompts should be stored using the `--prompts-dir` parameter:

```bash
# Use custom directory for prompts
computor-agent tutor --prompts-dir ./my-prompts

# Development mode with custom directory
computor-agent tutor --dev --prompts-dir /tmp/test-prompts

# Default location: ~/.computor/prompts
computor-agent tutor --dev
```

### 2. Automatic Initialization

When you specify a prompts directory:
- **Missing files are auto-created** with default content
- **Existing files are preserved** - never overwritten
- **Directory structure is created** automatically

This means you can:
1. Point to an empty directory → all prompts initialized
2. Point to a partial directory → only missing files created
3. Point to a complete directory → nothing changed

### 3. Hot Reload (Development Mode)

In development mode (`--dev`), changes to prompt files are detected automatically:

```bash
computor-agent tutor --dev --prompts-dir ./prompts
```

- Edit any `.md` file in the prompts directory
- See `🔄 Prompt reloaded: filename.md` in the CLI
- Changes take effect immediately
- No restart required

### 4. Directory Structure

```
prompts/
├── personality/          # Personality tone prompts
│   ├── friendly_professional.md
│   ├── strict.md
│   ├── casual.md
│   └── encouraging.md
├── strategy/            # Response strategy prompts
│   ├── question_example.md
│   ├── question_howto.md
│   ├── help_debug.md
│   ├── help_review.md
│   ├── clarification.md
│   └── fallback.md
└── security/           # Security check prompts
    ├── detection.md
    └── confirmation.md
```

## File Format

Each prompt file is a markdown file with optional YAML frontmatter:

```markdown
---
title: Strategy: question_howto
generated: true
editable: true
---

You are helping a student learn how to do something.

Assignment Context:
---
{assignment_description}
---

{personality_prompt}

The student is asking a general how-to question...
```

## Usage Examples

### Example 1: Project-Specific Prompts

Keep prompts with your project:

```bash
# Create project-specific prompts
mkdir -p ./project-prompts
computor-agent tutor --dev --prompts-dir ./project-prompts

# Files are auto-initialized on first run
# Edit them to customize behavior
vim ./project-prompts/personality/friendly_professional.md

# Changes apply immediately (hot reload)
```

### Example 2: Testing Different Prompt Sets

Test different prompt variations:

```bash
# Test set A
computor-agent tutor --dev --prompts-dir ./prompts-concise

# Test set B
computor-agent tutor --dev --prompts-dir ./prompts-verbose

# Compare results
```

### Example 3: Shared Team Prompts

Share prompts across team:

```bash
# Clone team prompts repo
git clone git@github.com:team/tutor-prompts.git

# Use team prompts
computor-agent tutor --prompts-dir ./tutor-prompts

# Changes tracked in version control
```

## Commands in Development Mode

When running with `--dev`:

- `/reload` - Manually reload all prompts
- `/show` - Show conversation history
- `/clear` - Clear messages
- `/exit` - Exit development mode

## Best Practices

1. **Version Control**: Store custom prompts in git for tracking changes
2. **Experimentation**: Use different directories for A/B testing
3. **Documentation**: Add comments in markdown files to explain prompt logic
4. **Conciseness**: All default prompts include length guidelines (2-3 paragraphs max)

## Implementation Details

### Initialization Logic

```python
def _ensure_prompt_files(prompts_dir: Path):
    """
    For each expected prompt file:
    1. Check if file exists
    2. If not, create with default content
    3. If yes, skip (preserve existing)
    """
```

### Load Priority

1. Check specified `--prompts-dir` (if provided)
2. Fall back to `~/.computor/prompts`
3. Fall back to hardcoded templates (if no files)

### Hot Reload Mechanism

- Uses `watchdog` library for file system monitoring
- Only active in development mode (`--dev`)
- Detects changes within 1 second
- Updates in-memory prompt cache
- No impact on agent performance

## Migration from Hardcoded Prompts

To migrate from the old hardcoded system:

```bash
# Export all defaults to a directory
python -m computor_agent.tutor.prompts.export_defaults ~/my-prompts

# Use the exported prompts
computor-agent tutor --prompts-dir ~/my-prompts

# Edit as needed
```

## Troubleshooting

### Prompts Not Loading

Check the console output for:
- `Loading prompts from: /path/to/prompts`
- `✓ Initialized N missing prompt files`

### Hot Reload Not Working

Ensure you're in development mode:
- Must use `--dev` flag
- Look for `Hot reload: Enabled` in startup message
- Check for `🔄 Prompt reloaded` messages

### Custom Prompts Overwritten

This should never happen. The system:
- ONLY creates missing files
- NEVER overwrites existing files
- Preserves all custom content

## Summary

The prompt configuration system provides:

✅ **Flexibility** - Use any directory for prompts
✅ **Safety** - Never overwrites existing files
✅ **Convenience** - Auto-initializes missing files
✅ **Speed** - Hot reload for instant testing
✅ **Portability** - Share prompts across projects/teams

This allows you to customize the tutor agent's behavior without touching code!