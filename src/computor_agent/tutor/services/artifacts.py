"""
Submission Artifacts Service for the Tutor AI Agent.

Handles listing, downloading, and extracting submission artifacts (ZIPs).
"""

import io
import logging
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class Artifact:
    """
    Metadata about a submission artifact.

    Attributes:
        id: Artifact ID
        submission_group_id: Parent submission group
        uploaded_at: When the artifact was uploaded
        uploaded_by_id: Course member who uploaded
        file_size: Size in bytes
        version_identifier: Version tag/identifier
        result: Test result (0.0 to 1.0) if tested
        is_latest: Whether this is the latest artifact
    """
    id: str
    submission_group_id: str
    uploaded_at: Optional[datetime] = None
    uploaded_by_id: Optional[str] = None
    file_size: int = 0
    version_identifier: Optional[str] = None
    result: Optional[float] = None
    is_latest: bool = False

    @property
    def has_result(self) -> bool:
        """Check if artifact has test results."""
        return self.result is not None

    @property
    def result_percentage(self) -> Optional[float]:
        """Get result as percentage (0-100)."""
        if self.result is None:
            return None
        return self.result * 100


@dataclass
class ArtifactContent:
    """
    Contents of an extracted artifact.

    Attributes:
        artifact: The artifact metadata
        files: Mapping of file path -> file content
        total_files: Total number of files extracted
        total_size: Total size of extracted content
        extraction_path: Where files were extracted (if saved to disk)
        truncated: Whether content was truncated due to limits
    """
    artifact: Artifact
    files: dict[str, str] = field(default_factory=dict)
    binary_files: list[str] = field(default_factory=list)
    total_files: int = 0
    total_size: int = 0
    extraction_path: Optional[Path] = None
    truncated: bool = False

    def get_file(self, path: str) -> Optional[str]:
        """Get content of a specific file."""
        return self.files.get(path)

    def list_files(self, extension: Optional[str] = None) -> list[str]:
        """
        List all files, optionally filtered by extension.

        Args:
            extension: Filter by extension (e.g., '.py')

        Returns:
            List of file paths
        """
        paths = list(self.files.keys())
        if extension:
            paths = [p for p in paths if p.endswith(extension)]
        return sorted(paths)

    def format_for_prompt(self, max_lines: int = 1000) -> str:
        """
        Format artifact content for LLM prompt.

        Args:
            max_lines: Maximum total lines to include

        Returns:
            Formatted string with file contents
        """
        parts = [f"=== Submission Artifact ({self.total_files} files) ===\n"]

        lines_remaining = max_lines

        for file_path in sorted(self.files.keys()):
            if lines_remaining <= 0:
                parts.append("\n... (truncated)")
                break

            content = self.files[file_path]
            file_lines = content.split("\n")

            if len(file_lines) > lines_remaining:
                content = "\n".join(file_lines[:lines_remaining])
                content += "\n... (file truncated)"
                lines_remaining = 0
            else:
                lines_remaining -= len(file_lines)

            parts.append(f"\n--- {file_path} ---\n{content}")

        if self.binary_files:
            parts.append(f"\n\nBinary files (not shown): {', '.join(self.binary_files)}")

        return "".join(parts)


class ArtifactsService:
    """
    Service for managing submission artifacts.

    Provides methods to:
    - List artifacts for a submission group
    - Download artifact ZIPs
    - Extract and read artifact contents
    - Save artifacts to local filesystem

    Usage:
        service = ArtifactsService(client)

        # List all artifacts
        artifacts = await service.list_artifacts(submission_group_id)

        # Get latest artifact
        latest = await service.get_latest_artifact(submission_group_id)

        # Download and extract
        content = await service.download_and_extract(artifact.id)

        # Save to disk
        path = await service.download_to_path(artifact.id, Path("/tmp/submission"))
    """

    # Code file extensions to read as text
    CODE_EXTENSIONS = {
        ".py", ".java", ".js", ".ts", ".jsx", ".tsx",
        ".c", ".cpp", ".h", ".hpp", ".cs", ".go", ".rs",
        ".rb", ".php", ".swift", ".kt", ".scala", ".sh",
        ".sql", ".html", ".css", ".scss", ".yaml", ".yml",
        ".json", ".xml", ".md", ".txt", ".toml", ".ini",
        ".cfg", ".conf", ".env", ".gitignore", ".dockerignore",
        "Makefile", "Dockerfile", "Jenkinsfile",
    }

    # Maximum file size to read as text (5MB)
    MAX_TEXT_FILE_SIZE = 5 * 1024 * 1024

    def __init__(self, client: Any) -> None:
        """
        Initialize the service.

        Args:
            client: ComputorClient instance
        """
        self.client = client

    async def list_artifacts(
        self,
        submission_group_id: str,
        *,
        limit: Optional[int] = None,
    ) -> list[Artifact]:
        """
        List all artifacts for a submission group.

        Args:
            submission_group_id: Submission group ID
            limit: Maximum number of artifacts to return

        Returns:
            List of Artifact objects, sorted by upload date (newest first)
        """
        try:
            artifacts = await self.client.submission_artifacts.list(
                submission_group_id=submission_group_id,
            )

            if not artifacts:
                return []

            # Convert to our model and sort
            result = []
            for a in artifacts:
                uploaded_at = None
                if hasattr(a, "uploaded_at") and a.uploaded_at:
                    if isinstance(a.uploaded_at, str):
                        try:
                            uploaded_at = datetime.fromisoformat(
                                a.uploaded_at.replace("Z", "+00:00")
                            )
                        except ValueError:
                            pass
                    else:
                        uploaded_at = a.uploaded_at

                # Get result from latest_result if available
                result_value = None
                latest_result = getattr(a, "latest_result", None)
                if latest_result:
                    result_value = getattr(latest_result, "result", None)

                result.append(Artifact(
                    id=a.id,
                    submission_group_id=submission_group_id,
                    uploaded_at=uploaded_at,
                    uploaded_by_id=getattr(a, "uploaded_by_course_member_id", None),
                    file_size=getattr(a, "file_size", 0) or 0,
                    version_identifier=getattr(a, "version_identifier", None),
                    result=result_value,
                ))

            # Sort by upload date, newest first
            result.sort(key=lambda x: x.uploaded_at or datetime.min, reverse=True)

            # Mark latest
            if result:
                result[0].is_latest = True

            if limit:
                result = result[:limit]

            return result

        except Exception as e:
            logger.warning(f"Failed to list artifacts for {submission_group_id}: {e}")
            return []

    async def get_latest_artifact(
        self,
        submission_group_id: str,
    ) -> Optional[Artifact]:
        """
        Get the most recent artifact for a submission group.

        Args:
            submission_group_id: Submission group ID

        Returns:
            Latest Artifact or None if no artifacts
        """
        artifacts = await self.list_artifacts(submission_group_id, limit=1)
        return artifacts[0] if artifacts else None

    async def download_and_extract(
        self,
        artifact_id: str,
        *,
        max_files: int = 50,
        max_total_size: int = 10 * 1024 * 1024,  # 10MB
    ) -> Optional[ArtifactContent]:
        """
        Download an artifact and extract its contents into memory.

        Args:
            artifact_id: Artifact ID
            max_files: Maximum number of files to extract
            max_total_size: Maximum total size to extract

        Returns:
            ArtifactContent with extracted files, or None on failure
        """
        try:
            # Download the ZIP
            buffer = await self._download_artifact(artifact_id)
            if not buffer:
                return None

            # Get artifact metadata
            artifact_meta = await self._get_artifact_metadata(artifact_id)
            if not artifact_meta:
                # Create minimal metadata
                artifact_meta = Artifact(
                    id=artifact_id,
                    submission_group_id="unknown",
                )

            # Extract contents
            return self._extract_zip(
                buffer,
                artifact_meta,
                max_files=max_files,
                max_total_size=max_total_size,
            )

        except Exception as e:
            logger.error(f"Failed to download/extract artifact {artifact_id}: {e}")
            return None

    async def download_to_path(
        self,
        artifact_id: str,
        destination: Path,
        *,
        overwrite: bool = False,
    ) -> Optional[Path]:
        """
        Download and extract artifact to a local directory.

        Args:
            artifact_id: Artifact ID
            destination: Destination directory
            overwrite: If True, remove existing directory first

        Returns:
            Path to extracted directory, or None on failure
        """
        try:
            destination = Path(destination)

            if destination.exists():
                if overwrite:
                    import shutil
                    shutil.rmtree(destination)
                else:
                    logger.warning(f"Destination already exists: {destination}")
                    return destination

            # Download the ZIP
            buffer = await self._download_artifact(artifact_id)
            if not buffer:
                return None

            # Create destination
            destination.mkdir(parents=True, exist_ok=True)

            # Extract to destination
            with zipfile.ZipFile(io.BytesIO(buffer)) as zf:
                zf.extractall(destination)

            return destination

        except Exception as e:
            logger.error(f"Failed to download artifact {artifact_id} to {destination}: {e}")
            return None

    async def _download_artifact(self, artifact_id: str) -> Optional[bytes]:
        """Download artifact ZIP as bytes."""
        try:
            # Use the client's download method
            buffer = await self.client.submission_artifacts.download(id=artifact_id)
            return buffer
        except Exception as e:
            logger.error(f"Failed to download artifact {artifact_id}: {e}")
            return None

    async def _get_artifact_metadata(self, artifact_id: str) -> Optional[Artifact]:
        """Get artifact metadata."""
        try:
            a = await self.client.submission_artifacts.get(id=artifact_id)
            if not a:
                return None

            uploaded_at = None
            if hasattr(a, "uploaded_at") and a.uploaded_at:
                if isinstance(a.uploaded_at, str):
                    try:
                        uploaded_at = datetime.fromisoformat(
                            a.uploaded_at.replace("Z", "+00:00")
                        )
                    except ValueError:
                        pass
                else:
                    uploaded_at = a.uploaded_at

            return Artifact(
                id=a.id,
                submission_group_id=getattr(a, "submission_group_id", "unknown"),
                uploaded_at=uploaded_at,
                uploaded_by_id=getattr(a, "uploaded_by_course_member_id", None),
                file_size=getattr(a, "file_size", 0) or 0,
                version_identifier=getattr(a, "version_identifier", None),
            )
        except Exception as e:
            logger.warning(f"Failed to get artifact metadata {artifact_id}: {e}")
            return None

    def _extract_zip(
        self,
        buffer: bytes,
        artifact: Artifact,
        *,
        max_files: int = 50,
        max_total_size: int = 10 * 1024 * 1024,
    ) -> ArtifactContent:
        """Extract ZIP buffer into ArtifactContent."""
        files: dict[str, str] = {}
        binary_files: list[str] = []
        total_size = 0
        truncated = False

        try:
            with zipfile.ZipFile(io.BytesIO(buffer)) as zf:
                infos = zf.infolist()

                for i, info in enumerate(infos):
                    # Skip directories
                    if info.is_dir():
                        continue

                    # Check file limit
                    if len(files) + len(binary_files) >= max_files:
                        truncated = True
                        break

                    # Check size limit
                    if total_size >= max_total_size:
                        truncated = True
                        break

                    # Skip very large files
                    if info.file_size > self.MAX_TEXT_FILE_SIZE:
                        binary_files.append(info.filename)
                        continue

                    # Check if it's a code/text file
                    filename = info.filename
                    suffix = Path(filename).suffix.lower()
                    name = Path(filename).name

                    is_text = (
                        suffix in self.CODE_EXTENSIONS
                        or name in self.CODE_EXTENSIONS
                    )

                    if not is_text:
                        binary_files.append(filename)
                        continue

                    # Read and decode
                    try:
                        content = zf.read(info).decode("utf-8", errors="replace")
                        files[filename] = content
                        total_size += len(content)
                    except Exception:
                        binary_files.append(filename)

        except zipfile.BadZipFile:
            logger.error("Invalid ZIP file")
            return ArtifactContent(artifact=artifact)

        return ArtifactContent(
            artifact=artifact,
            files=files,
            binary_files=binary_files,
            total_files=len(files) + len(binary_files),
            total_size=total_size,
            truncated=truncated,
        )

    async def compare_artifacts(
        self,
        artifact_id_1: str,
        artifact_id_2: str,
    ) -> dict[str, Any]:
        """
        Compare two artifacts and return differences.

        Args:
            artifact_id_1: First artifact ID (older)
            artifact_id_2: Second artifact ID (newer)

        Returns:
            Dict with added, removed, modified files
        """
        content1 = await self.download_and_extract(artifact_id_1)
        content2 = await self.download_and_extract(artifact_id_2)

        if not content1 or not content2:
            return {"error": "Failed to download artifacts"}

        files1 = set(content1.files.keys())
        files2 = set(content2.files.keys())

        added = files2 - files1
        removed = files1 - files2
        common = files1 & files2

        modified = []
        for f in common:
            if content1.files[f] != content2.files[f]:
                modified.append(f)

        return {
            "added": sorted(added),
            "removed": sorted(removed),
            "modified": sorted(modified),
            "unchanged": sorted(common - set(modified)),
        }
