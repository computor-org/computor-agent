"""
Figure detection helpers.

Single source of truth for deciding which files are reviewable images
and for reading them from disk with size/count caps. Used by the ZIP
extraction path (ArtifactsService) and all disk-walking loaders
(scenario loader, grading dev mode, repository walk).
"""

import logging
from pathlib import Path

from computor_agent.tutor.figures.models import FigureFile

logger = logging.getLogger(__name__)

# Raster image formats accepted by OpenAI-compatible vision endpoints
IMAGE_EXTENSIONS: set[str] = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}

_MEDIA_TYPES: dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
}

# Directories never scanned for figures
DEFAULT_SKIP_DIRS: set[str] = {
    ".git", ".svn", "__pycache__", "node_modules", ".venv", "venv",
    ".idea", ".vscode", ".pytest_cache", ".mypy_cache", ".ruff_cache",
}


def is_image_file(path: str | Path, extensions: set[str] | None = None) -> bool:
    """
    Check whether a path looks like a reviewable image file.

    Args:
        path: File path (string or Path)
        extensions: Extension set to match against (default: IMAGE_EXTENSIONS)

    Returns:
        True if the file suffix matches a known image extension
    """
    suffix = Path(path).suffix.lower()
    return suffix in (extensions if extensions is not None else IMAGE_EXTENSIONS)


def media_type_for(path: str | Path) -> str:
    """
    Get the MIME type for an image file path.

    Args:
        path: File path (string or Path)

    Returns:
        MIME type string (default "application/octet-stream" if unknown)
    """
    suffix = Path(path).suffix.lower()
    return _MEDIA_TYPES.get(suffix, "application/octet-stream")


def collect_images_from_dir(
    root: Path,
    *,
    extensions: set[str] | None = None,
    max_figures: int = 10,
    max_image_bytes: int = 5 * 1024 * 1024,
    skip_dirs: set[str] | None = None,
) -> tuple[list[FigureFile], list[str]]:
    """
    Recursively collect image files from a directory.

    Args:
        root: Directory to walk
        extensions: Image extensions to match (default: IMAGE_EXTENSIONS)
        max_figures: Maximum number of figures to collect
        max_image_bytes: Maximum size of a single image file
        skip_dirs: Directory names to skip (default: DEFAULT_SKIP_DIRS)

    Returns:
        Tuple of (collected figures, skipped file paths). Files beyond
        max_figures or over max_image_bytes are reported as skipped.
    """
    skip = skip_dirs if skip_dirs is not None else DEFAULT_SKIP_DIRS

    figures: list[FigureFile] = []
    skipped: list[str] = []

    if not root.is_dir():
        return figures, skipped

    for file_path in sorted(root.rglob("*")):
        if not file_path.is_file() or file_path.name.startswith("."):
            continue
        rel_parts = file_path.relative_to(root).parts
        if any(part in skip for part in rel_parts[:-1]):
            continue
        if not is_image_file(file_path, extensions):
            continue

        rel = str(file_path.relative_to(root))
        try:
            size = file_path.stat().st_size
            if size > max_image_bytes:
                logger.warning(
                    f"Skipping oversized figure {rel} ({size} > {max_image_bytes} bytes)"
                )
                skipped.append(rel)
                continue
            if len(figures) >= max_figures:
                skipped.append(rel)
                continue
            figures.append(
                FigureFile(
                    path=rel,
                    data=file_path.read_bytes(),
                    media_type=media_type_for(file_path),
                )
            )
        except OSError as e:
            logger.warning(f"Failed to read figure {rel}: {e}")
            skipped.append(rel)

    return figures, skipped
