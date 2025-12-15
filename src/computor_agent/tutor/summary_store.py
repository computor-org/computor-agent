"""
Summary storage for the Tutor AI Agent.

This is the AI's "memory" - notes it writes to itself to remember context
about students and conversations. When the AI picks up a new message,
it reads its previous notes to maintain continuity.

Storage structure:
    {base_dir}/
    ├── submission_group/
    │   ├── {sg-id-1}.json    # Notes about this submission group
    │   └── {sg-id-2}.json
    ├── student/
    │   └── {course-member-id}.json  # Notes about this student
    └── course/
        └── {course-id}.json  # Notes about this course
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentNote:
    """
    A note the AI writes to itself for future reference.

    When the AI finishes processing a message, it can write a summary
    of what happened and what it learned. Next time it processes a
    message for the same entity, it reads these notes first.
    """

    entity_type: str
    """Type of entity (e.g., 'submission_group', 'student', 'course')."""

    entity_id: str
    """ID of the entity."""

    note: str
    """The AI's note/summary about this interaction."""

    root_message_id: Optional[str] = None
    """The root message ID of the conversation this note is about."""

    topics: list[str] = field(default_factory=list)
    """Topics discussed (for quick reference)."""

    student_level: Optional[str] = None
    """AI's assessment of student's understanding level."""

    issues_resolved: list[str] = field(default_factory=list)
    """Issues that were resolved."""

    issues_pending: list[str] = field(default_factory=list)
    """Issues still pending/unresolved."""

    created_at: datetime = field(default_factory=datetime.now)
    """When this note was created."""

    metadata: dict = field(default_factory=dict)
    """Additional metadata."""

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "note": self.note,
            "root_message_id": self.root_message_id,
            "topics": self.topics,
            "student_level": self.student_level,
            "issues_resolved": self.issues_resolved,
            "issues_pending": self.issues_pending,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AgentNote":
        """Create from dictionary."""
        return cls(
            entity_type=data["entity_type"],
            entity_id=data["entity_id"],
            note=data.get("note", ""),
            root_message_id=data.get("root_message_id"),
            topics=data.get("topics", []),
            student_level=data.get("student_level"),
            issues_resolved=data.get("issues_resolved", []),
            issues_pending=data.get("issues_pending", []),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(),
            metadata=data.get("metadata", {}),
        )


class SummaryStore:
    """
    Persistent storage for the AI's notes to itself.

    The AI writes notes after processing interactions, and reads them
    before processing new ones. This gives the AI "memory" across sessions.

    Usage:
        store = SummaryStore(Path("~/.computor/summaries"))

        # Save a note after processing
        note = AgentNote(
            entity_type="submission_group",
            entity_id="sg-456",
            note="Student struggling with recursion. Explained base case concept.",
            topics=["recursion", "base case"],
            student_level="intermediate",
        )
        store.save(note)

        # Read notes before processing (AI reads its own notes)
        notes = store.load("submission_group", "sg-456", limit=3)
        latest = store.get_latest("submission_group", "sg-456")
    """

    def __init__(self, base_dir: Path) -> None:
        """
        Initialize the summary store.

        Args:
            base_dir: Base directory for storing summaries
        """
        self.base_dir = Path(base_dir).expanduser().resolve()

    def _get_entity_dir(self, entity_type: str) -> Path:
        """Get the directory for an entity type."""
        return self.base_dir / entity_type

    def _get_entity_file(self, entity_type: str, entity_id: str) -> Path:
        """Get the file path for an entity."""
        # Sanitize entity_id to be filesystem-safe
        safe_id = entity_id.replace("/", "_").replace("\\", "_")
        return self._get_entity_dir(entity_type) / f"{safe_id}.json"

    def save(self, note: AgentNote) -> None:
        """
        Save an agent note.

        Appends to the list of notes for this entity.

        Args:
            note: The note to save
        """
        file_path = self._get_entity_file(note.entity_type, note.entity_id)

        # Ensure directory exists
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Load existing notes
        notes = self._load_file(file_path)

        # Append new note
        notes.append(note.to_dict())

        # Write back
        try:
            with open(file_path, "w") as f:
                json.dump(notes, f, indent=2)

            logger.debug(
                f"Saved note for {note.entity_type}/{note.entity_id}"
            )
        except Exception as e:
            logger.error(f"Failed to save note to {file_path}: {e}")
            raise

    def load(
        self,
        entity_type: str,
        entity_id: str,
        limit: Optional[int] = None,
    ) -> list[AgentNote]:
        """
        Load notes for an entity.

        Args:
            entity_type: The entity type (e.g., 'submission_group')
            entity_id: The entity ID
            limit: Maximum number of notes to return (newest first)

        Returns:
            List of AgentNote objects, newest first
        """
        file_path = self._get_entity_file(entity_type, entity_id)
        data = self._load_file(file_path)

        # Convert to objects
        notes = [AgentNote.from_dict(d) for d in data]

        # Sort by created_at descending (newest first)
        notes.sort(key=lambda n: n.created_at, reverse=True)

        if limit:
            notes = notes[:limit]

        return notes

    def get_latest(
        self,
        entity_type: str,
        entity_id: str,
    ) -> Optional[AgentNote]:
        """
        Get the most recent note for an entity.

        Args:
            entity_type: The entity type
            entity_id: The entity ID

        Returns:
            The most recent AgentNote or None
        """
        notes = self.load(entity_type, entity_id, limit=1)
        return notes[0] if notes else None

    def get_for_context(
        self,
        entity_type: str,
        entity_id: str,
        max_notes: int = 3,
    ) -> str:
        """
        Get notes formatted for inclusion in AI context/prompt.

        This is what the AI reads to remember previous interactions.

        Args:
            entity_type: The entity type
            entity_id: The entity ID
            max_notes: Maximum notes to include

        Returns:
            Formatted string for AI context, or empty string if no notes
        """
        notes = self.load(entity_type, entity_id, limit=max_notes)

        if not notes:
            return ""

        lines = ["Previous notes about this context:"]
        for i, note in enumerate(notes, 1):
            date_str = note.created_at.strftime("%Y-%m-%d %H:%M")
            lines.append(f"\n[Note {i} from {date_str}]")
            lines.append(note.note)

            if note.topics:
                lines.append(f"Topics: {', '.join(note.topics)}")
            if note.student_level:
                lines.append(f"Student level: {note.student_level}")
            if note.issues_pending:
                lines.append(f"Pending issues: {', '.join(note.issues_pending)}")

        return "\n".join(lines)

    def exists(self, entity_type: str, entity_id: str) -> bool:
        """Check if any notes exist for an entity."""
        file_path = self._get_entity_file(entity_type, entity_id)
        return file_path.exists()

    def count(self, entity_type: str, entity_id: str) -> int:
        """Count notes for an entity."""
        file_path = self._get_entity_file(entity_type, entity_id)
        data = self._load_file(file_path)
        return len(data)

    def delete(self, entity_type: str, entity_id: str) -> bool:
        """
        Delete all notes for an entity.

        Args:
            entity_type: The entity type
            entity_id: The entity ID

        Returns:
            True if deleted, False if didn't exist
        """
        file_path = self._get_entity_file(entity_type, entity_id)

        if file_path.exists():
            file_path.unlink()
            logger.info(f"Deleted notes for {entity_type}/{entity_id}")
            return True

        return False

    def list_entities(self, entity_type: str) -> list[str]:
        """
        List all entity IDs with notes of a given type.

        Args:
            entity_type: The entity type

        Returns:
            List of entity IDs
        """
        entity_dir = self._get_entity_dir(entity_type)

        if not entity_dir.exists():
            return []

        return [
            f.stem  # filename without extension
            for f in entity_dir.glob("*.json")
            if f.is_file()
        ]

    def _load_file(self, file_path: Path) -> list[dict]:
        """Load notes from a file."""
        if not file_path.exists():
            return []

        try:
            with open(file_path) as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except json.JSONDecodeError as e:
            logger.warning(f"Invalid JSON in {file_path}: {e}")
            return []
        except Exception as e:
            logger.error(f"Failed to load {file_path}: {e}")
            return []

    def get_stats(self) -> dict:
        """Get storage statistics."""
        stats = {
            "base_dir": str(self.base_dir),
            "entity_types": {},
        }

        if not self.base_dir.exists():
            return stats

        for entity_dir in self.base_dir.iterdir():
            if entity_dir.is_dir():
                entity_type = entity_dir.name
                files = list(entity_dir.glob("*.json"))
                stats["entity_types"][entity_type] = {
                    "entities": len(files),
                    "files": [f.stem for f in files[:10]],  # First 10
                }

        return stats


# Keep backward compatibility aliases
ConversationSummary = AgentNote
