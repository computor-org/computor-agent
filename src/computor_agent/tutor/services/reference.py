"""
Reference Solution Service for the Tutor AI Agent.

Fetches reference solutions and generates comparisons/diffs
between student code and expected solutions.
"""

import difflib
import io
import logging
import zipfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class DiffLineType(str, Enum):
    """Type of diff line."""
    CONTEXT = "context"    # Unchanged line
    ADDED = "added"        # Line added in student code
    REMOVED = "removed"    # Line missing from student code
    CHANGED = "changed"    # Line modified


@dataclass
class DiffLine:
    """A single line in a diff."""
    line_number_old: Optional[int]
    line_number_new: Optional[int]
    line_type: DiffLineType
    content: str


@dataclass
class FileDiff:
    """
    Diff between student and reference version of a file.

    Attributes:
        file_path: Path to the file
        student_exists: Whether file exists in student code
        reference_exists: Whether file exists in reference
        lines: List of diff lines
        additions: Number of lines added
        deletions: Number of lines removed
        similarity: Similarity score (0.0 to 1.0)
    """
    file_path: str
    student_exists: bool = True
    reference_exists: bool = True
    lines: list[DiffLine] = field(default_factory=list)
    additions: int = 0
    deletions: int = 0
    similarity: float = 1.0

    @property
    def is_identical(self) -> bool:
        """Check if files are identical."""
        return self.additions == 0 and self.deletions == 0

    @property
    def is_missing_in_student(self) -> bool:
        """Check if file is missing from student code."""
        return self.reference_exists and not self.student_exists

    @property
    def is_extra_in_student(self) -> bool:
        """Check if file is extra in student code (not in reference)."""
        return self.student_exists and not self.reference_exists

    def get_unified_diff(self, context_lines: int = 3) -> str:
        """Get diff in unified diff format."""
        if self.is_identical:
            return ""

        if self.is_missing_in_student:
            return f"File missing in student code: {self.file_path}"

        if self.is_extra_in_student:
            return f"Extra file in student code: {self.file_path}"

        # Build unified diff output
        lines = []
        lines.append(f"--- reference/{self.file_path}")
        lines.append(f"+++ student/{self.file_path}")

        current_hunk: list[str] = []
        hunk_start_old = 0
        hunk_start_new = 0

        for diff_line in self.lines:
            if diff_line.line_type == DiffLineType.CONTEXT:
                current_hunk.append(f" {diff_line.content}")
            elif diff_line.line_type == DiffLineType.REMOVED:
                current_hunk.append(f"-{diff_line.content}")
            elif diff_line.line_type == DiffLineType.ADDED:
                current_hunk.append(f"+{diff_line.content}")

        if current_hunk:
            lines.extend(current_hunk)

        return "\n".join(lines)


@dataclass
class ReferenceComparison:
    """
    Complete comparison between student code and reference solution.

    Attributes:
        file_diffs: List of file diffs
        total_files: Total files compared
        identical_files: Number of identical files
        modified_files: Number of modified files
        missing_files: Files in reference but not in student
        extra_files: Files in student but not in reference
        overall_similarity: Overall code similarity (0.0 to 1.0)
    """
    file_diffs: list[FileDiff] = field(default_factory=list)
    total_files: int = 0
    identical_files: int = 0
    modified_files: int = 0
    missing_files: list[str] = field(default_factory=list)
    extra_files: list[str] = field(default_factory=list)
    overall_similarity: float = 0.0

    def get_modified_diffs(self) -> list[FileDiff]:
        """Get only diffs for modified files."""
        return [d for d in self.file_diffs if not d.is_identical]

    def get_critical_differences(self) -> list[FileDiff]:
        """
        Get diffs for files with significant differences.

        Files with similarity < 0.8 or missing/extra files.
        """
        critical = []
        for diff in self.file_diffs:
            if diff.similarity < 0.8 or diff.is_missing_in_student:
                critical.append(diff)
        return critical

    def format_for_prompt(
        self,
        max_diffs: int = 5,
        max_lines_per_diff: int = 50,
    ) -> str:
        """
        Format comparison for LLM prompt.

        Args:
            max_diffs: Maximum number of file diffs to include
            max_lines_per_diff: Maximum lines per file diff

        Returns:
            Formatted string for LLM context
        """
        parts = [
            "=== Reference Comparison ===",
            f"Overall Similarity: {self.overall_similarity:.1%}",
            f"Files: {self.identical_files}/{self.total_files} identical",
        ]

        if self.missing_files:
            parts.append(f"\nMissing files ({len(self.missing_files)}):")
            for f in self.missing_files[:5]:
                parts.append(f"  - {f}")
            if len(self.missing_files) > 5:
                parts.append(f"  ... and {len(self.missing_files) - 5} more")

        if self.extra_files:
            parts.append(f"\nExtra files ({len(self.extra_files)}):")
            for f in self.extra_files[:5]:
                parts.append(f"  + {f}")
            if len(self.extra_files) > 5:
                parts.append(f"  ... and {len(self.extra_files) - 5} more")

        modified = self.get_modified_diffs()
        if modified:
            parts.append(f"\nModified files ({len(modified)}):")

            for i, diff in enumerate(modified[:max_diffs]):
                parts.append(f"\n--- {diff.file_path} ---")
                parts.append(f"Similarity: {diff.similarity:.1%}")
                parts.append(f"+{diff.additions} -{diff.deletions} lines")

                # Add diff content
                unified = diff.get_unified_diff()
                if unified:
                    lines = unified.split("\n")
                    if len(lines) > max_lines_per_diff:
                        lines = lines[:max_lines_per_diff]
                        lines.append("... (diff truncated)")
                    parts.append("\n".join(lines))

            if len(modified) > max_diffs:
                parts.append(f"\n... and {len(modified) - max_diffs} more modified files")

        return "\n".join(parts)

    def get_summary(self) -> str:
        """Get a brief summary of the comparison."""
        if self.overall_similarity >= 0.95:
            return "Student code closely matches reference solution."
        elif self.overall_similarity >= 0.7:
            return f"Student code is {self.overall_similarity:.0%} similar to reference, with modifications in {self.modified_files} files."
        elif self.overall_similarity >= 0.4:
            return f"Significant differences from reference ({self.overall_similarity:.0%} similarity). {len(self.missing_files)} missing files, {self.modified_files} modified."
        else:
            return f"Student code differs substantially from reference ({self.overall_similarity:.0%} similarity)."


class ReferenceService:
    """
    Service for fetching and comparing reference solutions.

    Provides methods to:
    - Download reference solutions
    - Compare student code with reference
    - Generate detailed diffs
    - Format comparisons for LLM context

    Usage:
        service = ReferenceService(client)

        # Download reference for course content
        ref_path = await service.download_reference(course_content_id, destination)

        # Compare student code with reference
        comparison = service.compare_code(student_files, reference_files)

        # Or compare from paths
        comparison = await service.compare_from_paths(student_path, reference_path)
    """

    # Code file extensions to compare
    CODE_EXTENSIONS = {
        ".py", ".java", ".js", ".ts", ".jsx", ".tsx",
        ".c", ".cpp", ".h", ".hpp", ".cs", ".go", ".rs",
        ".rb", ".php", ".swift", ".kt", ".scala", ".sh",
        ".sql", ".html", ".css", ".scss", ".yaml", ".yml",
        ".json", ".xml", ".md", ".txt",
    }

    def __init__(self, client: Any) -> None:
        """
        Initialize the service.

        Args:
            client: ComputorClient instance
        """
        self.client = client

    async def download_reference(
        self,
        course_content_id: str,
        destination: Path,
        *,
        overwrite: bool = False,
    ) -> Optional[Path]:
        """
        Download reference solution for a course content.

        Args:
            course_content_id: Course content ID
            destination: Destination directory
            overwrite: Whether to overwrite existing

        Returns:
            Path to extracted reference, or None on failure
        """
        try:
            destination = Path(destination)

            if destination.exists() and not overwrite:
                logger.info(f"Reference already exists at {destination}")
                return destination

            if destination.exists():
                import shutil
                shutil.rmtree(destination)

            # Download the reference ZIP
            buffer = await self.client.course_contents.download_reference(
                id=course_content_id,
            )

            if not buffer:
                logger.warning(f"No reference available for {course_content_id}")
                return None

            # Extract to destination
            destination.mkdir(parents=True, exist_ok=True)

            with zipfile.ZipFile(io.BytesIO(buffer)) as zf:
                zf.extractall(destination)

            logger.info(f"Reference extracted to {destination}")
            return destination

        except Exception as e:
            logger.error(f"Failed to download reference for {course_content_id}: {e}")
            return None

    async def get_reference_files(
        self,
        course_content_id: str,
    ) -> Optional[dict[str, str]]:
        """
        Download reference and return as dict of files.

        Args:
            course_content_id: Course content ID

        Returns:
            Dict of file_path -> content, or None on failure
        """
        try:
            buffer = await self.client.course_contents.download_reference(
                id=course_content_id,
            )

            if not buffer:
                return None

            return self._extract_zip_to_dict(buffer)

        except Exception as e:
            logger.error(f"Failed to get reference files for {course_content_id}: {e}")
            return None

    def compare_code(
        self,
        student_files: dict[str, str],
        reference_files: dict[str, str],
        *,
        include_extra: bool = True,
    ) -> ReferenceComparison:
        """
        Compare student code with reference solution.

        Args:
            student_files: Dict of student file_path -> content
            reference_files: Dict of reference file_path -> content
            include_extra: Include files only in student code

        Returns:
            ReferenceComparison with detailed analysis
        """
        file_diffs: list[FileDiff] = []
        identical_count = 0
        modified_count = 0
        missing_files: list[str] = []
        extra_files: list[str] = []

        all_files = set(student_files.keys()) | set(reference_files.keys())

        # Filter to code files only
        code_files = {
            f for f in all_files
            if Path(f).suffix.lower() in self.CODE_EXTENSIONS
        }

        total_similarity = 0.0
        compared_count = 0

        for file_path in sorted(code_files):
            student_content = student_files.get(file_path)
            reference_content = reference_files.get(file_path)

            if reference_content is None:
                # Extra file in student code
                if include_extra:
                    extra_files.append(file_path)
                    file_diffs.append(FileDiff(
                        file_path=file_path,
                        student_exists=True,
                        reference_exists=False,
                    ))
                continue

            if student_content is None:
                # Missing file in student code
                missing_files.append(file_path)
                file_diffs.append(FileDiff(
                    file_path=file_path,
                    student_exists=False,
                    reference_exists=True,
                    similarity=0.0,
                ))
                compared_count += 1
                continue

            # Compare the files
            diff = self._compare_files(file_path, student_content, reference_content)
            file_diffs.append(diff)

            if diff.is_identical:
                identical_count += 1
            else:
                modified_count += 1

            total_similarity += diff.similarity
            compared_count += 1

        overall_similarity = (
            total_similarity / compared_count if compared_count > 0 else 0.0
        )

        return ReferenceComparison(
            file_diffs=file_diffs,
            total_files=len(code_files),
            identical_files=identical_count,
            modified_files=modified_count,
            missing_files=missing_files,
            extra_files=extra_files,
            overall_similarity=overall_similarity,
        )

    async def compare_from_paths(
        self,
        student_path: Path,
        reference_path: Path,
    ) -> ReferenceComparison:
        """
        Compare code from filesystem paths.

        Args:
            student_path: Path to student code
            reference_path: Path to reference code

        Returns:
            ReferenceComparison with detailed analysis
        """
        student_files = self._read_directory(student_path)
        reference_files = self._read_directory(reference_path)

        return self.compare_code(student_files, reference_files)

    def _compare_files(
        self,
        file_path: str,
        student_content: str,
        reference_content: str,
    ) -> FileDiff:
        """Compare two file contents and generate diff."""
        student_lines = student_content.splitlines(keepends=True)
        reference_lines = reference_content.splitlines(keepends=True)

        # Calculate similarity
        matcher = difflib.SequenceMatcher(None, reference_content, student_content)
        similarity = matcher.ratio()

        # Generate diff
        diff_lines: list[DiffLine] = []
        additions = 0
        deletions = 0

        differ = difflib.unified_diff(
            reference_lines,
            student_lines,
            lineterm="",
        )

        line_num_old = 0
        line_num_new = 0

        for line in differ:
            # Skip headers
            if line.startswith("---") or line.startswith("+++"):
                continue

            # Parse hunk headers
            if line.startswith("@@"):
                # Extract line numbers from @@ -start,count +start,count @@
                import re
                match = re.match(r"@@ -(\d+)", line)
                if match:
                    line_num_old = int(match.group(1))
                match = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)", line)
                if match:
                    line_num_new = int(match.group(1))
                continue

            content = line[1:] if line else ""

            if line.startswith("-"):
                diff_lines.append(DiffLine(
                    line_number_old=line_num_old,
                    line_number_new=None,
                    line_type=DiffLineType.REMOVED,
                    content=content,
                ))
                deletions += 1
                line_num_old += 1
            elif line.startswith("+"):
                diff_lines.append(DiffLine(
                    line_number_old=None,
                    line_number_new=line_num_new,
                    line_type=DiffLineType.ADDED,
                    content=content,
                ))
                additions += 1
                line_num_new += 1
            elif line.startswith(" "):
                diff_lines.append(DiffLine(
                    line_number_old=line_num_old,
                    line_number_new=line_num_new,
                    line_type=DiffLineType.CONTEXT,
                    content=content,
                ))
                line_num_old += 1
                line_num_new += 1

        return FileDiff(
            file_path=file_path,
            student_exists=True,
            reference_exists=True,
            lines=diff_lines,
            additions=additions,
            deletions=deletions,
            similarity=similarity,
        )

    def _read_directory(self, path: Path) -> dict[str, str]:
        """Read all code files from a directory."""
        files: dict[str, str] = {}

        if not path.exists():
            return files

        for file_path in path.rglob("*"):
            if file_path.is_dir():
                continue

            # Skip hidden files and common non-code directories
            rel_path = file_path.relative_to(path)
            parts = rel_path.parts

            if any(p.startswith(".") for p in parts):
                continue
            if any(p in ("node_modules", "__pycache__", "venv", ".venv") for p in parts):
                continue

            # Only read code files
            if file_path.suffix.lower() not in self.CODE_EXTENSIONS:
                continue

            try:
                content = file_path.read_text(errors="replace")
                files[str(rel_path)] = content
            except Exception as e:
                logger.debug(f"Could not read {file_path}: {e}")

        return files

    def _extract_zip_to_dict(self, buffer: bytes) -> dict[str, str]:
        """Extract ZIP to dict of file_path -> content."""
        files: dict[str, str] = {}

        try:
            with zipfile.ZipFile(io.BytesIO(buffer)) as zf:
                for info in zf.infolist():
                    if info.is_dir():
                        continue

                    # Only read code files
                    suffix = Path(info.filename).suffix.lower()
                    if suffix not in self.CODE_EXTENSIONS:
                        continue

                    try:
                        content = zf.read(info).decode("utf-8", errors="replace")
                        files[info.filename] = content
                    except Exception:
                        pass

        except zipfile.BadZipFile:
            logger.error("Invalid ZIP file")

        return files
