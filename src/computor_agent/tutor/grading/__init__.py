"""
Grading module for the Tutor Agent.

This module provides automated grading of student submissions based on:
- Assignment description/README
- Reference solution
- Student submission

The grading produces:
- A grade (float 0.0-1.0, where 1.0 = 100%)
- A status (corrected, correction_necessary, improvement_possible)
- Detailed feedback for the student
"""

from computor_agent.tutor.grading.models import (
    GradingStatus,
    GradingResult,
    GradingContext,
)
from computor_agent.tutor.grading.grader import SubmissionGrader

__all__ = [
    "GradingStatus",
    "GradingResult",
    "GradingContext",
    "SubmissionGrader",
]
