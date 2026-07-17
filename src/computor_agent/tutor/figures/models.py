"""
Data models for figure review.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class FigureFile:
    """
    An image file found in a student submission.

    Attributes:
        path: Relative path within the submission
        data: Raw image bytes
        media_type: MIME type, e.g. "image/png"
    """

    path: str
    data: bytes
    media_type: str

    @property
    def size(self) -> int:
        """Size of the image in bytes."""
        return len(self.data)

    def __repr__(self) -> str:
        return (
            f"FigureFile(path={self.path!r}, media_type={self.media_type!r}, "
            f"size={self.size})"
        )


@dataclass
class FigureReview:
    """
    Result of reviewing a single figure with the vision LLM.

    Attributes:
        path: Path of the reviewed figure
        success: Whether the review completed (False = LLM call failed)
        assessment: Free-text quality assessment
        issues: Specific problems found in the figure
        score: Optional quality score (0.0-1.0, 1.0 = flawless)
        error: Error description when success is False
    """

    path: str
    success: bool
    assessment: str = ""
    issues: list[str] = field(default_factory=list)
    score: Optional[float] = None
    error: Optional[str] = None


@dataclass
class FigureReviewSummary:
    """
    Combined result of reviewing all figures in a submission.

    Attributes:
        reviews: Per-figure review results (including failed ones)
        skipped: Figure paths not reviewed due to limits (count/size caps)
    """

    reviews: list[FigureReview] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    @property
    def reviewed_count(self) -> int:
        """Number of figures successfully reviewed."""
        return sum(1 for r in self.reviews if r.success)

    @property
    def has_content(self) -> bool:
        """Whether there is anything to report."""
        return bool(self.reviews or self.skipped)

    def format_for_prompt(self) -> str:
        """Format the review results as a text section for LLM prompts."""
        parts = [
            f"=== Figure Review ({len(self.reviews)} figure(s), "
            "analyzed by a vision model) ==="
        ]

        for review in self.reviews:
            parts.append(f"\n--- {review.path} ---")
            if not review.success:
                parts.append(f"(Could not be reviewed: {review.error})")
                continue
            if review.assessment:
                parts.append(f"Assessment: {review.assessment}")
            if review.score is not None:
                parts.append(f"Quality score: {review.score:.2f} (0.0-1.0)")
            if review.issues:
                parts.append("Issues:")
                parts.extend(f"- {issue}" for issue in review.issues)
            elif review.assessment:
                parts.append("Issues: none")

        if self.skipped:
            parts.append(
                f"\nFigures not reviewed (limits exceeded): {', '.join(self.skipped)}"
            )

        return "\n".join(parts)
