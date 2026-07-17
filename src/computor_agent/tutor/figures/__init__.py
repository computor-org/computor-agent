"""
Figure review for the Tutor AI Agent.

Detects figures (plots/images) in student submissions and reviews them
with a vision-capable LLM. Shared by the tutor messaging flow and the
grading flow.
"""

from computor_agent.tutor.figures.detection import (
    IMAGE_EXTENSIONS,
    collect_images_from_dir,
    is_image_file,
    media_type_for,
)
from computor_agent.tutor.figures.models import (
    FigureFile,
    FigureReview,
    FigureReviewSummary,
)
from computor_agent.tutor.figures.service import (
    FigureReviewService,
    build_figure_reviewer,
)

__all__ = [
    "IMAGE_EXTENSIONS",
    "is_image_file",
    "media_type_for",
    "collect_images_from_dir",
    "FigureFile",
    "FigureReview",
    "FigureReviewSummary",
    "FigureReviewService",
    "build_figure_reviewer",
]
