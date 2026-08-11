"""
Submission Artifacts Service for the Tutor AI Agent.

Handles listing, downloading, and extracting submission artifacts (ZIPs).
"""

import asyncio
import io
import logging
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from computor_client.exceptions import ComputorClientError, NotFoundError
from computor_types.artifacts import SubmissionArtifactGet

from computor_agent.tutor.figures.detection import is_image_file, media_type_for
from computor_agent.tutor.figures.models import FigureFile

logger = logging.getLogger(__name__)


@dataclass
class ExtractedSubmissionContent:
    """
    Contents of an extracted submission artifact ZIP.

    This is custom extraction logic not provided by computor-types.

    Attributes:
        artifact: The artifact metadata from API
        files: Mapping of file path -> file content
        image_files: Image files collected for figure review (if enabled)
        total_files: Total number of files extracted
        total_size: Total size of extracted content
        extraction_path: Where files were extracted (if saved to disk)
        truncated: Whether content was truncated due to limits
    """
    artifact: SubmissionArtifactGet
    files: dict[str, str] = field(default_factory=dict)
    binary_files: list[str] = field(default_factory=list)
    image_files: list[FigureFile] = field(default_factory=list)
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

        if self.image_files:
            names = ", ".join(f.path for f in self.image_files)
            parts.append(f"\n\nFigures (reviewed separately): {names}")

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
    ) -> list[SubmissionArtifactGet]:
        """
        List all artifacts for a submission group.

        Note: This may return limited data depending on API availability.

        Args:
            submission_group_id: Submission group ID
            limit: Maximum number of artifacts to return

        Returns:
            List of Artifact objects, sorted by upload date (newest first)
        """
        result = []

        try:
            try:
                artifacts = await self.client.submissions.list_artifacts(
                    submission_group_id=submission_group_id,
                )
                if artifacts:
                    result = artifacts
                    # Sort by upload date if available, newest first
                    if hasattr(result[0], 'uploaded_at'):
                        result.sort(key=lambda x: x.uploaded_at or datetime.min, reverse=True)
            except ComputorClientError as e:
                logger.debug(f"submissions.list_artifacts failed: {e}")

            if limit:
                result = result[:limit]

            return result

        except Exception as e:
            logger.warning(f"Failed to list artifacts for {submission_group_id}: {e}")
            return []

    async def get_latest_artifact(
        self,
        submission_group_id: str,
    ) -> Optional[SubmissionArtifactGet]:
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
        collect_images: bool = False,
        image_extensions: Optional[set[str]] = None,
        max_figures: int = 10,
        max_image_bytes: int = 5 * 1024 * 1024,
    ) -> Optional[ExtractedSubmissionContent]:
        """
        Download an artifact and extract its contents into memory.

        Args:
            artifact_id: Artifact ID
            max_files: Maximum number of files to extract
            max_total_size: Maximum total size to extract
            collect_images: Also collect image files for figure review
            image_extensions: Image extensions to collect (default set if None)
            max_figures: Maximum number of images to collect
            max_image_bytes: Maximum size per image file

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
                # Create minimal metadata with required fields
                artifact_meta = SubmissionArtifactGet(
                    id=artifact_id,
                    submission_group_id="unknown",
                    file_size=len(buffer) if buffer else 0,
                    bucket_name="unknown",
                    object_key="unknown",
                    uploaded_at=datetime.now(),
                )

            # Extract contents
            return self._extract_zip(
                buffer,
                artifact_meta,
                max_files=max_files,
                max_total_size=max_total_size,
                collect_images=collect_images,
                image_extensions=image_extensions,
                max_figures=max_figures,
                max_image_bytes=max_image_bytes,
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
            buffer = await self.client.submissions.get_artifacts_download_by_artifact_id(
                artifact_id
            )
        except ComputorClientError as e:
            logger.error(f"Failed to download artifact {artifact_id}: {e}")
            return None

        if not buffer:
            logger.warning(f"Empty download for artifact {artifact_id}")
        return buffer

    async def _get_artifact_metadata(self, artifact_id: str) -> Optional[SubmissionArtifactGet]:
        """Get artifact metadata."""
        try:
            return await self.client.submissions.get_artifacts(artifact_id)
        except ComputorClientError as e:
            logger.warning(f"Failed to get artifact metadata {artifact_id}: {e}")
            return None

    def _extract_zip(
        self,
        buffer: bytes,
        artifact: SubmissionArtifactGet,
        *,
        max_files: int = 50,
        max_total_size: int = 10 * 1024 * 1024,
        collect_images: bool = False,
        image_extensions: Optional[set[str]] = None,
        max_figures: int = 10,
        max_image_bytes: int = 5 * 1024 * 1024,
    ) -> ExtractedSubmissionContent:
        """Extract ZIP buffer into ExtractedSubmissionContent.

        With collect_images=True, image files are read into image_files
        (for figure review) instead of being listed as binary; images have
        their own count/size caps and don't count against max_total_size.
        """
        files: dict[str, str] = {}
        binary_files: list[str] = []
        image_files: list[FigureFile] = []
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
                    if len(files) + len(binary_files) + len(image_files) >= max_files:
                        truncated = True
                        break

                    # Check size limit
                    if total_size >= max_total_size:
                        truncated = True
                        break

                    filename = info.filename

                    # Collect image files for figure review
                    if collect_images and is_image_file(filename, image_extensions):
                        if (
                            info.file_size > max_image_bytes
                            or len(image_files) >= max_figures
                        ):
                            binary_files.append(filename)
                            continue
                        try:
                            image_files.append(
                                FigureFile(
                                    path=filename,
                                    data=zf.read(info),
                                    media_type=media_type_for(filename),
                                )
                            )
                        except Exception:
                            binary_files.append(filename)
                        continue

                    # Skip very large files
                    if info.file_size > self.MAX_TEXT_FILE_SIZE:
                        binary_files.append(filename)
                        continue

                    # Check if it's a code/text file
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
            return ExtractedSubmissionContent(artifact=artifact)

        return ExtractedSubmissionContent(
            artifact=artifact,
            files=files,
            binary_files=binary_files,
            image_files=image_files,
            total_files=len(files) + len(binary_files) + len(image_files),
            total_size=total_size,
            truncated=truncated,
        )

    async def download_latest_submission(
        self,
        *,
        submission_group_id: Optional[str] = None,
        course_content_id: Optional[str] = None,
        course_member_id: Optional[str] = None,
        version_identifier: Optional[str] = None,
        submit_only: bool = False,
        max_files: int = 50,
        max_total_size: int = 10 * 1024 * 1024,
        collect_images: bool = False,
        image_extensions: Optional[set[str]] = None,
        max_figures: int = 10,
        max_image_bytes: int = 5 * 1024 * 1024,
    ) -> Optional[ExtractedSubmissionContent]:
        """
        Download the latest submission using the /submissions/artifacts/download endpoint.

        Args:
            submission_group_id: Submission group ID (use this OR course_content_id+course_member_id)
            course_content_id: Course content ID (use with course_member_id)
            course_member_id: Course member ID (use with course_content_id)
            version_identifier: Optional version identifier
            submit_only: If True, only download official submissions. If False, include test uploads
            max_files: Maximum number of files to extract
            max_total_size: Maximum total size to extract
            collect_images: Also collect image files for figure review
            image_extensions: Image extensions to collect (default set if None)
            max_figures: Maximum number of images to collect
            max_image_bytes: Maximum size per image file

        Returns:
            ArtifactContent with extracted files, or None if no submission found
        """
        try:
            # Validate parameters
            if submission_group_id:
                # Use submission_group_id
                params = {
                    "submission_group_id": submission_group_id,
                    "submit_only": submit_only,
                }
                logger.debug(f"Using submission_group_id for download: {submission_group_id}")
            elif course_content_id and course_member_id:
                # Use course_content_id + course_member_id
                params = {
                    "course_content_id": course_content_id,
                    "course_member_id": course_member_id,
                    "submit_only": submit_only,
                }
                logger.debug(f"Using course_content_id + course_member_id: {course_content_id}, {course_member_id}")
            else:
                logger.error("Must provide either submission_group_id OR (course_content_id + course_member_id)")
                return None

            if version_identifier:
                params["version_identifier"] = version_identifier

            buffer = None
            try:
                logger.info(f"Attempting to download submission with params: {params}")
                # GET /submissions/artifacts/download returns the ZIP bytes.
                buffer = await self.client.submissions.get_artifacts_download(**params)
                if buffer:
                    logger.info(f"Downloaded submission, size: {len(buffer)} bytes")
                else:
                    logger.warning("Artifact download returned an empty body")
            except NotFoundError:
                logger.info("No submission artifact exists yet for the given parameters")
            except ComputorClientError as e:
                logger.error(f"Artifact download failed: {e}", exc_info=True)

            if not buffer:
                logger.info("No submission artifact found for the given parameters")
                return None

            # Create minimal metadata since we don't have full artifact details
            # Create a SubmissionArtifactGet with required fields
            artifact_meta = SubmissionArtifactGet(
                id=f"latest-{submission_group_id or f'{course_content_id}-{course_member_id}'}",
                submission_group_id=submission_group_id or "unknown",
                file_size=len(buffer) if buffer else 0,
                bucket_name="unknown",
                object_key="unknown",
                uploaded_at=datetime.now(),
            )

            # Extract contents
            return self._extract_zip(
                buffer,
                artifact_meta,
                max_files=max_files,
                max_total_size=max_total_size,
                collect_images=collect_images,
                image_extensions=image_extensions,
                max_figures=max_figures,
                max_image_bytes=max_image_bytes,
            )

        except Exception as e:
            logger.error(f"Failed to download latest submission: {e}")
            return None

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
