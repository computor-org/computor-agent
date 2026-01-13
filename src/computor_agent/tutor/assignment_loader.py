"""
Assignment loader for development mode.

Loads assignment context from a reference solution directory structure:
- meta.yaml: Contains assignment metadata and file lists
- content/index.md or content/index_<language>.md: Assignment description
- Student submission files (from properties.studentSubmissionFiles)
- Additional files (from properties.additionalFiles)

Files with "_master." in the name are ignored (development/test files).
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)


@dataclass
class AssignmentFile:
    """A file that is part of the assignment."""

    path: str
    """Relative path within the assignment directory."""

    content: str
    """File content."""

    is_submission_file: bool = False
    """True if this is a student submission file."""


@dataclass
class AssignmentContext:
    """Context loaded from an assignment directory."""

    identifier: str
    """Assignment identifier (directory name, e.g., 'itpcp.pgph.py.basis1')."""

    title: str
    """Assignment title from meta.yaml."""

    description: str
    """Assignment description from meta.yaml."""

    language: str
    """Language code (e.g., 'de', 'en')."""

    readme_content: str
    """Content of the README/index.md file."""

    files: list[AssignmentFile] = field(default_factory=list)
    """List of relevant assignment files."""

    slug: str = ""
    """Full slug from meta.yaml."""

    def get_submission_files(self) -> list[AssignmentFile]:
        """Get only the student submission files."""
        return [f for f in self.files if f.is_submission_file]

    def get_all_code(self) -> str:
        """Get all code files concatenated for context."""
        parts = []
        for f in self.files:
            if f.path.endswith('.py'):
                parts.append(f"# File: {f.path}\n{f.content}")
        return "\n\n".join(parts)

    def to_context_string(self) -> str:
        """Format as a context string for the LLM."""
        parts = [
            f"## Assignment: {self.title}",
            f"Identifier: {self.identifier}",
            f"Language: {self.language}",
            "",
            "### Description",
            self.readme_content,
        ]

        submission_files = self.get_submission_files()
        if submission_files:
            parts.append("")
            parts.append("### Reference Solution Files")
            for f in submission_files:
                parts.append(f"\n#### {f.path}")
                parts.append(f"```python\n{f.content}\n```")

        return "\n".join(parts)


class AssignmentLoader:
    """
    Loads assignment context from a reference solution directory.

    Directory structure expected:
        <assignment_dir>/
            meta.yaml           # Assignment metadata
            content/
                index.md        # Default README
                index_en.md     # English README (optional)
                index_de.md     # German README (optional)
            *.py                # Python files

    Usage:
        # Load directly from assignment path
        context = AssignmentLoader.load_from_path("/path/to/assignment")

        # Or use instance for multiple assignments
        loader = AssignmentLoader("/path/to/reference/repo")
        context = loader.load("itpcp.pgph.py.basis1")
    """

    @classmethod
    def load_from_path(
        cls, assignment_path: Path, language: Optional[str] = None
    ) -> AssignmentContext:
        """
        Load an assignment directly from its path.

        Args:
            assignment_path: Path to the assignment directory (must contain meta.yaml)
            language: Preferred language for README (None = use meta.yaml language)

        Returns:
            AssignmentContext with all loaded data
        """
        assignment_path = Path(assignment_path)

        if not assignment_path.exists():
            raise ValueError(f"Assignment path does not exist: {assignment_path}")

        if not assignment_path.is_dir():
            raise ValueError(f"Assignment path is not a directory: {assignment_path}")

        meta_path = assignment_path / "meta.yaml"
        if not meta_path.exists():
            raise ValueError(f"meta.yaml not found in: {assignment_path}")

        # Create a temporary loader with parent as reference path
        loader = cls(assignment_path.parent)
        return loader.load(assignment_path.name, language)

    def __init__(self, reference_path: Path):
        """
        Initialize the loader.

        Args:
            reference_path: Path to the reference solution repository
        """
        self.reference_path = Path(reference_path)

        if not self.reference_path.exists():
            raise ValueError(f"Reference path does not exist: {reference_path}")

        if not self.reference_path.is_dir():
            raise ValueError(f"Reference path is not a directory: {reference_path}")

    def list_assignments(self) -> list[str]:
        """
        List all available assignment identifiers.

        Returns:
            List of assignment directory names
        """
        assignments = []

        for item in self.reference_path.iterdir():
            if item.is_dir() and not item.name.startswith('.'):
                meta_path = item / "meta.yaml"
                if meta_path.exists():
                    assignments.append(item.name)

        return sorted(assignments)

    def load(self, identifier: str, language: Optional[str] = None) -> AssignmentContext:
        """
        Load an assignment by its identifier.

        Args:
            identifier: Assignment directory name
            language: Preferred language for README (None = use meta.yaml language)

        Returns:
            AssignmentContext with all loaded data

        Raises:
            ValueError: If assignment not found or meta.yaml invalid
        """
        assignment_dir = self.reference_path / identifier

        if not assignment_dir.exists():
            raise ValueError(f"Assignment not found: {identifier}")

        meta_path = assignment_dir / "meta.yaml"
        if not meta_path.exists():
            raise ValueError(f"meta.yaml not found in: {identifier}")

        # Load meta.yaml
        with open(meta_path) as f:
            meta = yaml.safe_load(f)

        if not meta:
            raise ValueError(f"Empty or invalid meta.yaml in: {identifier}")

        # Extract metadata
        title = meta.get("title", identifier)
        description = meta.get("description", "")
        meta_language = meta.get("language", "en")
        slug = meta.get("slug", identifier)

        # Use provided language or fall back to meta language
        lang = language or meta_language

        # Load README content
        readme_content = self._load_readme(assignment_dir, lang)

        # Load files
        files = self._load_files(assignment_dir, meta)

        return AssignmentContext(
            identifier=identifier,
            title=title,
            description=description,
            language=lang,
            readme_content=readme_content,
            files=files,
            slug=slug,
        )

    def _load_readme(self, assignment_dir: Path, language: str) -> str:
        """Load the README/index file for the assignment."""
        content_dir = assignment_dir / "content"

        if not content_dir.exists():
            logger.warning(f"No content directory in {assignment_dir}")
            return "(No assignment description available)"

        # Try language-specific file first
        readme_paths = [
            content_dir / f"index_{language}.md",
            content_dir / f"README_{language}.md",
            content_dir / "index.md",
            content_dir / "README.md",
        ]

        for path in readme_paths:
            if path.exists():
                try:
                    return path.read_text()
                except Exception as e:
                    logger.warning(f"Failed to read {path}: {e}")

        logger.warning(f"No README found in {content_dir}")
        return "(No assignment description available)"

    def _load_files(self, assignment_dir: Path, meta: dict) -> list[AssignmentFile]:
        """Load relevant assignment files."""
        files = []

        properties = meta.get("properties", {})
        submission_files = set(properties.get("studentSubmissionFiles", []))
        additional_files = set(properties.get("additionalFiles", []))

        # All relevant file paths
        relevant_paths = submission_files | additional_files

        for rel_path in relevant_paths:
            file_path = assignment_dir / rel_path

            # Skip master files
            if "_master." in rel_path:
                continue

            if not file_path.exists():
                logger.warning(f"File not found: {file_path}")
                continue

            try:
                content = file_path.read_text()
                files.append(AssignmentFile(
                    path=rel_path,
                    content=content,
                    is_submission_file=rel_path in submission_files,
                ))
            except Exception as e:
                logger.warning(f"Failed to read {file_path}: {e}")

        return files

    def load_by_slug(self, slug: str, language: Optional[str] = None) -> Optional[AssignmentContext]:
        """
        Load an assignment by its slug (from meta.yaml).

        Args:
            slug: The slug value from meta.yaml
            language: Preferred language

        Returns:
            AssignmentContext or None if not found
        """
        for identifier in self.list_assignments():
            try:
                context = self.load(identifier, language)
                if context.slug == slug:
                    return context
            except Exception:
                continue

        return None
