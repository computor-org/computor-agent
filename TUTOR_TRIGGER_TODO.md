# Tutor Agent Trigger System - Work in Progress

## Current Status (2026-01-11)

The tutor agent is mostly working, but there's a critical issue with tag-based trigger detection.

## Problem

**The agent responds to ALL unread messages, not just messages with the configured trigger tags.**

The issue is that the API's `tags` filter parameter in the messages endpoint doesn't seem to filter correctly. When we call:

```python
request_messages = await self.messages.list(
    submission_group_id=submission_group_id,
    tags=self.config.request_tag_strings,  # e.g., ["ai::help"]
    tags_match_all=self.config.require_all_tags,
    unread=True,
)
```

The API returns ALL unread messages regardless of the `tags` filter.

## Action Required

**Extend the backend messages endpoint** to properly support tag filtering:

1. The `/messages` list endpoint needs to accept and filter by `tags` parameter
2. Tags format: `scope::value` (e.g., `ai::help`, `ai::support`)
3. The endpoint should only return messages that have the specified tag(s)
4. Consider `tags_match_all` parameter: if `True`, require ALL tags; if `False`, require ANY tag

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
- Response tag: `#ai::support` - AI adds this to its responses to avoid responding to itself

## What's Working

1. **Security checks** - Rewritten prompts reduce false positives (normal student questions no longer flagged as attacks)
2. **Follow-up triggers** - Only responds to direct replies to AI messages (parent must have response_tag in title)
3. **AI self-detection** - Filters out AI's own messages by checking for response_tag in title
4. **LLM verbose logging** - Debug logging shows LLM requests/responses when `--verbose` flag is used

## Files Modified

| File | Changes |
|------|---------|
| `src/computor_agent/tutor/trigger.py` | Added debug logging, stricter follow-up detection, AI message filtering |
| `src/computor_agent/tutor/prompts/templates.py` | Rewrote security prompts to reduce false positives |
| `src/computor_agent/llm/openai_provider.py` | Added verbose logging for LLM requests/responses |

## Key Code Locations

- **Trigger detection**: `src/computor_agent/tutor/trigger.py`
  - `_check_new_conversation_trigger()` - checks for messages with request tags (line ~206)
  - `_check_follow_up_trigger()` - checks for replies to AI messages (line ~267)

- **Scheduler**: `src/computor_agent/tutor/scheduler.py`
  - `_process_course_content()` - calls trigger checker when unread messages exist (line ~454)

- **Config**: `src/computor_agent/tutor/config.py`
  - `TriggerTag` class - defines tag format with scope/value (line ~218)
  - `TriggerConfig` class - holds request_tags and response_tag (line ~258)

## Next Steps

1. **Backend**: Implement proper tag filtering in the messages list endpoint
2. **Test**: Verify that `messages.list(tags=["ai::help"])` only returns tagged messages
3. **Verify**: Run the tutor agent and confirm it only responds to properly tagged messages

## Testing the Fix

After implementing the backend changes:

```bash
# Run with verbose logging to see trigger decisions
computor-agent tutor --verbose

# Check the logs for:
# - "API returned X messages for tags=['ai::help']"
# - Should be 0 if no messages have the tag
# - Should only include messages that actually have #ai::help in them
```

## Debug Logging Added

The trigger checker now logs:
- Which tags it's searching for
- How many messages the API returns
- Each message's title
- How many remain after filtering AI responses
