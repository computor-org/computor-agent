"""
Modular services for the Tutor AI Agent.

This module provides various services that can be used by the tutor agent
for gathering context, analyzing submissions, and generating feedback.

Services:
    - test_results: Fetch and parse test result JSON for detailed feedback
    - artifacts: List, download, and extract submission artifacts
    - reference: Fetch reference solutions and generate comparisons/diffs
    - history: Track submission history and student improvements
    - comments: Read and write tutor comments about students
    - progress: Fetch course and member progress metrics

Each service is designed to be:
    - Modular: Can be used independently
    - Async: All API calls are async
    - Typed: Full type hints for IDE support
    - Testable: Can be mocked for unit tests
"""

from computor_agent.tutor.services.test_results import (
    TestResultsService,
    TestResult,
    TestCase,
    TestSuite,
    TestStatus,
)
from computor_agent.tutor.services.artifacts import (
    ArtifactsService,
    Artifact,
    ArtifactContent,
)
from computor_agent.tutor.services.reference import (
    ReferenceService,
    ReferenceComparison,
    FileDiff,
    DiffLine,
)
from computor_agent.tutor.services.history import (
    HistoryService,
    SubmissionHistory,
    SubmissionAttempt,
    ImprovementAnalysis,
)
from computor_agent.tutor.services.comments import (
    CommentsService,
    TutorComment,
)
from computor_agent.tutor.services.progress import (
    ProgressService,
    CourseProgress,
    MemberProgress,
    ContentProgress,
)

__all__ = [
    # Test Results
    "TestResultsService",
    "TestResult",
    "TestCase",
    "TestSuite",
    "TestStatus",
    # Artifacts
    "ArtifactsService",
    "Artifact",
    "ArtifactContent",
    # Reference
    "ReferenceService",
    "ReferenceComparison",
    "FileDiff",
    "DiffLine",
    # History
    "HistoryService",
    "SubmissionHistory",
    "SubmissionAttempt",
    "ImprovementAnalysis",
    # Comments
    "CommentsService",
    "TutorComment",
    # Progress
    "ProgressService",
    "CourseProgress",
    "MemberProgress",
    "ContentProgress",
]
