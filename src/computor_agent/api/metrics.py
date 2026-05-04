"""Counters and last-activity timestamps for the dashboard.

Single-process, asyncio-only — no locking required.
Timestamps are ISO-8601 UTC strings to keep JSON / template rendering
trivial.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class CourseMetrics:
    seen: int = 0
    succeeded: int = 0
    failed: int = 0
    skipped: int = 0
    last_seen_at: Optional[str] = None
    last_succeeded_at: Optional[str] = None
    last_failed_at: Optional[str] = None


class MetricsCollector:
    """Lightweight in-memory counters for the dashboard."""

    def __init__(self) -> None:
        self._started_at: str = _now()
        self.events_received: int = 0
        self.messages_seen: int = 0
        self.messages_succeeded: int = 0
        self.messages_failed: int = 0
        self.messages_skipped: int = 0
        self.last_event_at: Optional[str] = None
        self.last_catchup_at: Optional[str] = None
        self.last_seen_at: Optional[str] = None
        self.last_succeeded_at: Optional[str] = None
        self.last_failed_at: Optional[str] = None
        self._per_course: dict[str, CourseMetrics] = defaultdict(CourseMetrics)

    @property
    def started_at(self) -> str:
        return self._started_at

    def event_received(self) -> None:
        self.events_received += 1
        self.last_event_at = _now()

    def catchup_complete(self) -> None:
        self.last_catchup_at = _now()

    def message_seen(self, course_id: Optional[str] = None) -> None:
        self.messages_seen += 1
        ts = _now()
        self.last_seen_at = ts
        if course_id:
            cm = self._per_course[course_id]
            cm.seen += 1
            cm.last_seen_at = ts

    def message_succeeded(self, course_id: Optional[str] = None) -> None:
        self.messages_succeeded += 1
        ts = _now()
        self.last_succeeded_at = ts
        if course_id:
            cm = self._per_course[course_id]
            cm.succeeded += 1
            cm.last_succeeded_at = ts

    def message_failed(self, course_id: Optional[str] = None) -> None:
        self.messages_failed += 1
        ts = _now()
        self.last_failed_at = ts
        if course_id:
            cm = self._per_course[course_id]
            cm.failed += 1
            cm.last_failed_at = ts

    def message_skipped(self, course_id: Optional[str] = None) -> None:
        self.messages_skipped += 1
        if course_id:
            self._per_course[course_id].skipped += 1

    def snapshot(self) -> dict:
        return {
            "started_at": self._started_at,
            "events_received": self.events_received,
            "messages_seen": self.messages_seen,
            "messages_succeeded": self.messages_succeeded,
            "messages_failed": self.messages_failed,
            "messages_skipped": self.messages_skipped,
            "last_event_at": self.last_event_at,
            "last_catchup_at": self.last_catchup_at,
            "last_seen_at": self.last_seen_at,
            "last_succeeded_at": self.last_succeeded_at,
            "last_failed_at": self.last_failed_at,
            "per_course": {
                cid: {
                    "seen": cm.seen,
                    "succeeded": cm.succeeded,
                    "failed": cm.failed,
                    "skipped": cm.skipped,
                    "last_seen_at": cm.last_seen_at,
                    "last_succeeded_at": cm.last_succeeded_at,
                    "last_failed_at": cm.last_failed_at,
                }
                for cid, cm in self._per_course.items()
            },
        }
