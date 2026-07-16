"""Shared error types and helpers for the tutor agent."""


class AuthFatalError(RuntimeError):
    """Authentication has failed repeatedly and cannot recover without
    operator intervention (fresh credentials, restart)."""


def is_auth_error(exc: BaseException) -> bool:
    """Best-effort check whether an exception is a 401/unauthorized error.

    The computor-client surfaces auth failures either as httpx errors with a
    response attached or as plain exceptions with the status in the message,
    so both shapes are checked.
    """
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if status == 401:
        return True
    text = str(exc)
    return "401" in text or "Unauthorized" in text
