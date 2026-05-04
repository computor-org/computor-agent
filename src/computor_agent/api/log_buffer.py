"""In-memory ring buffer for log records, surfaced by the dashboard.

The dashboard reads from this buffer rather than tailing a log file —
the file (when `--log-file` is set) is the durable record on disk; the
buffer is what the live UI shows so the two never drift, and the UI
works even without a log file configured.
"""

from __future__ import annotations

import logging
from collections import deque
from threading import Lock
from typing import Optional


class LogBuffer(logging.Handler):
    """Bounded ring of formatted log lines."""

    DEFAULT_FORMAT = "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s"
    DEFAULT_DATEFMT = "%Y-%m-%d %H:%M:%S"

    def __init__(self, capacity: int = 2000) -> None:
        super().__init__()
        self._lines: deque[str] = deque(maxlen=capacity)
        # Logging records may arrive from worker threads (uvicorn, watchdog,
        # etc.), so guard the deque even though deque.append is itself atomic.
        self._lock = Lock()
        self.setFormatter(
            logging.Formatter(self.DEFAULT_FORMAT, datefmt=self.DEFAULT_DATEFMT)
        )

    def emit(self, record: logging.LogRecord) -> None:
        try:
            line = self.format(record)
        except Exception:
            self.handleError(record)
            return
        with self._lock:
            self._lines.append(line)

    def tail(self, n: int) -> list[str]:
        with self._lock:
            snap = list(self._lines)
        return snap[-n:] if n < len(snap) else snap

    def __len__(self) -> int:
        with self._lock:
            return len(self._lines)


_LOG_BUFFER: Optional[LogBuffer] = None


def get_log_buffer(capacity: int = 2000) -> LogBuffer:
    """Module-level singleton — same instance across CLI setup and API."""
    global _LOG_BUFFER
    if _LOG_BUFFER is None:
        _LOG_BUFFER = LogBuffer(capacity=capacity)
    return _LOG_BUFFER
