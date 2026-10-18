"""Explicit opt-in for logging LLM prompts and replies.

Prompts and model replies contain student input, code and tutor answers, so they
are never logged by default, not even at DEBUG (``--verbose``). They are only
dumped after ``--log-llm-content`` (or ``COMPUTOR_LOG_LLM_CONTENT=1``) is given.
"""

_log_llm_content = False


def set_log_llm_content(enabled: bool) -> None:
    """Enable or disable content dumps in the LLM provider debug logs."""
    global _log_llm_content
    _log_llm_content = bool(enabled)


def log_llm_content_enabled() -> bool:
    """Return True only if content logging was explicitly requested."""
    return _log_llm_content
