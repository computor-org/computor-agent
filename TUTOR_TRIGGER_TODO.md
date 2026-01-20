# Tutor Agent Trigger System - Work in Progress

## Current Status (2026-01-13)

The tutor agent is mostly working. The trigger system now uses a **tag-based model** where the agent only responds to messages that have the configured request tag.

## Current Behavior

**Tag-based response model:**
- The agent responds ONLY to messages that have a request tag in the title (e.g., `#ai::help`)
- User must explicitly add the tag to request help
- No automatic follow-up conversations
- This keeps the agent focused and prevents unwanted responses

## Known Issue

**The API's `tags` filter may not work correctly.**

When we call:
```python
request_messages = await self.messages.list(
    submission_group_id=submission_group_id,
    tags=self.config.request_tag_strings,  # e.g., ["ai::help"]
    unread=True,
)
```

The API might return ALL unread messages regardless of the `tags` filter. This needs to be verified/fixed in the backend.

## Action Required (Backend)

Verify/implement proper tag filtering in the messages endpoint:

1. The `/messages` list endpoint needs to accept and filter by `tags` parameter
2. Tags format: `scope::value` (e.g., `ai::help`, `ai::support`)
3. The endpoint should only return messages that have the specified tag(s)

## Current Configuration

In `config.yaml`:
```yaml
tutor:
  triggers:
    request_tags:
      - scope: "ai"
        value: "help"
    response_tag:
      scope: "ai"
        value: "support"
```

- Request tag: `#ai::help` - messages with this tag trigger the AI to respond
- Response tag: `#ai::support` - AI adds this to its responses to identify itself

## Recent Updates

### Development Mode
- Interactive shell for testing without API calls (`--dev` flag)
- Hot reload for prompt files
- See [docs/tutor-dev-mode.md](docs/tutor-dev-mode.md)

### Prompt Configuration
- Prompts now loaded from markdown files
- Auto-initialization of missing prompt files
- Customizable prompts directory (`--prompts-dir`)
- See [docs/prompt-configuration.md](docs/prompt-configuration.md)

### Trigger System Simplification
- Removed follow-up conversation logic
- Now uses simple tag-based triggering only
- User must add tag each time they want a response

## Key Files

| File | Purpose |
|------|---------|
| `src/computor_agent/tutor/trigger.py` | Tag-based trigger detection |
| `src/computor_agent/tutor/dev_mode.py` | Development mode with mock client |
| `src/computor_agent/tutor/prompts/loader.py` | Prompt file loading with hot reload |
| `docs/tutor-dev-mode.md` | Development mode documentation |
| `docs/prompt-configuration.md` | Prompt system documentation |

## Testing

### Development Mode
```bash
# Run with dev mode (no API calls)
python -m computor_agent.cli.main tutor --dev

# With verbose logging
python -m computor_agent.cli.main tutor --dev -v
```

### Production Mode
```bash
# Run with verbose logging to see trigger decisions
python -m computor_agent.cli.main tutor --verbose

# Check logs for:
# - "API returned X messages for tags=['ai::help']"
# - Should only return messages that have the request tag
```
