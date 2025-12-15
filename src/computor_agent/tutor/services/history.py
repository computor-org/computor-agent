"""
Submission History Service for the Tutor AI Agent.

Tracks submission history and analyzes student improvement over time.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class SubmissionAttempt:
    """
    A single submission attempt.

    Attributes:
        artifact_id: The artifact ID
        uploaded_at: When it was uploaded
        result: Test result (0.0 to 1.0)
        file_count: Number of files in submission
        has_tests_passed: Whether all tests passed
    """
    artifact_id: str
    uploaded_at: Optional[datetime] = None
    result: Optional[float] = None
    file_count: int = 0
    has_tests_passed: bool = False

    @property
    def result_percentage(self) -> Optional[float]:
        """Get result as percentage."""
        if self.result is None:
            return None
        return self.result * 100


@dataclass
class ImprovementAnalysis:
    """
    Analysis of improvement between submissions.

    Attributes:
        improved: Whether there was improvement
        result_change: Change in test result
        result_change_percent: Change as percentage points
        files_added: Number of new files
        files_removed: Number of removed files
        attempts_to_pass: Number of attempts before passing (if passed)
        trend: 'improving', 'declining', 'stable', 'fluctuating'
    """
    improved: bool = False
    result_change: float = 0.0
    result_change_percent: float = 0.0
    files_added: int = 0
    files_removed: int = 0
    attempts_to_pass: Optional[int] = None
    trend: str = "stable"
    message: str = ""

    def format_for_prompt(self) -> str:
        """Format analysis for LLM context."""
        parts = [f"Trend: {self.trend}"]

        if self.result_change != 0:
            direction = "improved" if self.result_change > 0 else "decreased"
            parts.append(
                f"Result {direction} by {abs(self.result_change_percent):.1f} percentage points"
            )

        if self.attempts_to_pass:
            parts.append(f"Passed after {self.attempts_to_pass} attempts")

        if self.message:
            parts.append(self.message)

        return "\n".join(parts)


@dataclass
class SubmissionHistory:
    """
    Complete submission history for a student/assignment.

    Attributes:
        submission_group_id: The submission group ID
        attempts: List of submission attempts, ordered by date
        total_attempts: Total number of submissions
        first_submission: First submission date
        last_submission: Most recent submission date
        best_result: Highest test result achieved
        current_result: Most recent test result
        analysis: Improvement analysis
    """
    submission_group_id: str
    attempts: list[SubmissionAttempt] = field(default_factory=list)
    total_attempts: int = 0
    first_submission: Optional[datetime] = None
    last_submission: Optional[datetime] = None
    best_result: Optional[float] = None
    current_result: Optional[float] = None
    analysis: Optional[ImprovementAnalysis] = None

    @property
    def has_multiple_attempts(self) -> bool:
        """Check if there are multiple submission attempts."""
        return len(self.attempts) > 1

    @property
    def has_improved(self) -> bool:
        """Check if student improved from first to latest."""
        if len(self.attempts) < 2:
            return False
        first_result = self.attempts[0].result
        last_result = self.attempts[-1].result
        if first_result is None or last_result is None:
            return False
        return last_result > first_result

    @property
    def is_passing(self) -> bool:
        """Check if latest submission passes (result >= 1.0)."""
        return self.current_result is not None and self.current_result >= 1.0

    def get_result_progression(self) -> list[float]:
        """Get list of results over time."""
        return [a.result for a in self.attempts if a.result is not None]

    def format_for_prompt(self) -> str:
        """Format history for LLM prompt."""
        if not self.attempts:
            return "No submission history available."

        parts = [
            f"=== Submission History ({self.total_attempts} attempts) ===",
        ]

        if self.first_submission and self.last_submission:
            parts.append(f"First: {self.first_submission.strftime('%Y-%m-%d %H:%M')}")
            parts.append(f"Latest: {self.last_submission.strftime('%Y-%m-%d %H:%M')}")

        if self.best_result is not None:
            parts.append(f"Best result: {self.best_result:.1%}")

        if self.current_result is not None:
            parts.append(f"Current result: {self.current_result:.1%}")

        # Show progression
        results = self.get_result_progression()
        if len(results) > 1:
            progression = " → ".join(f"{r:.0%}" for r in results[-5:])
            parts.append(f"\nRecent progression: {progression}")

        if self.analysis:
            parts.append(f"\n{self.analysis.format_for_prompt()}")

        return "\n".join(parts)


class HistoryService:
    """
    Service for tracking submission history and student improvement.

    Provides methods to:
    - Get submission history for a submission group
    - Analyze improvement trends
    - Generate feedback based on progress

    Usage:
        service = HistoryService(client)

        # Get history
        history = await service.get_history(submission_group_id)

        # Check improvement
        if history.has_improved:
            print(f"Improved by {history.analysis.result_change_percent}%")

        # Format for LLM
        formatted = history.format_for_prompt()
    """

    def __init__(self, client: Any) -> None:
        """
        Initialize the service.

        Args:
            client: ComputorClient instance
        """
        self.client = client

    async def get_history(
        self,
        submission_group_id: str,
        *,
        include_analysis: bool = True,
    ) -> SubmissionHistory:
        """
        Get complete submission history for a submission group.

        Args:
            submission_group_id: Submission group ID
            include_analysis: Whether to include improvement analysis

        Returns:
            SubmissionHistory with all attempts and analysis
        """
        try:
            # List all artifacts
            artifacts = await self.client.submission_artifacts.list(
                submission_group_id=submission_group_id,
            )

            if not artifacts:
                return SubmissionHistory(submission_group_id=submission_group_id)

            # Convert to attempts and sort by date
            attempts = []
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

                # Get result
                result = None
                latest_result = getattr(a, "latest_result", None)
                if latest_result:
                    result = getattr(latest_result, "result", None)

                attempts.append(SubmissionAttempt(
                    artifact_id=a.id,
                    uploaded_at=uploaded_at,
                    result=result,
                    has_tests_passed=result is not None and result >= 1.0,
                ))

            # Sort by upload date (oldest first)
            attempts.sort(key=lambda x: x.uploaded_at or datetime.max)

            # Calculate statistics
            results = [a.result for a in attempts if a.result is not None]

            history = SubmissionHistory(
                submission_group_id=submission_group_id,
                attempts=attempts,
                total_attempts=len(attempts),
                first_submission=attempts[0].uploaded_at if attempts else None,
                last_submission=attempts[-1].uploaded_at if attempts else None,
                best_result=max(results) if results else None,
                current_result=attempts[-1].result if attempts else None,
            )

            if include_analysis and len(attempts) >= 2:
                history.analysis = self._analyze_improvement(attempts)

            return history

        except Exception as e:
            logger.warning(f"Failed to get history for {submission_group_id}: {e}")
            return SubmissionHistory(submission_group_id=submission_group_id)

    async def get_improvement_message(
        self,
        submission_group_id: str,
    ) -> Optional[str]:
        """
        Get a human-friendly message about student's improvement.

        Args:
            submission_group_id: Submission group ID

        Returns:
            Improvement message or None if no history
        """
        history = await self.get_history(submission_group_id)

        if not history.attempts:
            return None

        if len(history.attempts) == 1:
            if history.is_passing:
                return "Great job! Your first submission passes all tests."
            elif history.current_result is not None:
                return f"This is your first submission with {history.current_result:.0%} of tests passing."
            else:
                return "This is your first submission."

        # Multiple attempts
        analysis = history.analysis
        if not analysis:
            return None

        if analysis.trend == "improving":
            if history.is_passing:
                return (
                    f"Excellent progress! After {history.total_attempts} attempts, "
                    f"you've achieved a passing score. "
                    f"Your result improved by {analysis.result_change_percent:.1f} percentage points."
                )
            else:
                return (
                    f"Good progress! Your result improved by "
                    f"{analysis.result_change_percent:.1f} percentage points "
                    f"over {history.total_attempts} attempts."
                )

        elif analysis.trend == "stable":
            if history.is_passing:
                return "Your submissions consistently pass all tests."
            else:
                return (
                    f"Your results have been stable at around {history.current_result:.0%}. "
                    f"Consider reviewing the failing tests for improvement opportunities."
                )

        elif analysis.trend == "declining":
            return (
                f"Your recent results have declined by "
                f"{abs(analysis.result_change_percent):.1f} percentage points. "
                f"Consider reviewing your recent changes."
            )

        elif analysis.trend == "fluctuating":
            return (
                f"Your results have been inconsistent across {history.total_attempts} attempts. "
                f"Best: {history.best_result:.0%}, Current: {history.current_result:.0%}."
            )

        return analysis.message if analysis.message else None

    def _analyze_improvement(
        self,
        attempts: list[SubmissionAttempt],
    ) -> ImprovementAnalysis:
        """Analyze improvement trend across attempts."""
        if len(attempts) < 2:
            return ImprovementAnalysis()

        # Get results that have values
        results = [(a, a.result) for a in attempts if a.result is not None]

        if len(results) < 2:
            return ImprovementAnalysis()

        first_result = results[0][1]
        last_result = results[-1][1]

        result_change = last_result - first_result
        improved = result_change > 0

        # Calculate trend
        trend = self._calculate_trend(results)

        # Find attempts to pass
        attempts_to_pass = None
        for i, (attempt, result) in enumerate(results):
            if result >= 1.0:
                attempts_to_pass = i + 1
                break

        # Generate message
        message = self._generate_trend_message(trend, results, attempts_to_pass)

        return ImprovementAnalysis(
            improved=improved,
            result_change=result_change,
            result_change_percent=result_change * 100,
            attempts_to_pass=attempts_to_pass,
            trend=trend,
            message=message,
        )

    def _calculate_trend(
        self,
        results: list[tuple[SubmissionAttempt, float]],
    ) -> str:
        """Calculate the overall trend from results."""
        if len(results) < 2:
            return "stable"

        values = [r[1] for r in results]

        # Check for consistent improvement
        improving_count = sum(
            1 for i in range(1, len(values))
            if values[i] > values[i - 1]
        )
        declining_count = sum(
            1 for i in range(1, len(values))
            if values[i] < values[i - 1]
        )
        stable_count = sum(
            1 for i in range(1, len(values))
            if abs(values[i] - values[i - 1]) < 0.01
        )

        total_changes = len(values) - 1

        if improving_count > total_changes * 0.6:
            return "improving"
        elif declining_count > total_changes * 0.6:
            return "declining"
        elif stable_count > total_changes * 0.6:
            return "stable"
        else:
            return "fluctuating"

    def _generate_trend_message(
        self,
        trend: str,
        results: list[tuple[SubmissionAttempt, float]],
        attempts_to_pass: Optional[int],
    ) -> str:
        """Generate a human-friendly trend message."""
        first_result = results[0][1]
        last_result = results[-1][1]
        best_result = max(r[1] for r in results)

        if trend == "improving":
            if last_result >= 1.0:
                if attempts_to_pass == len(results):
                    return "Achieved passing score on the final attempt."
                else:
                    return f"Achieved passing score after {attempts_to_pass} attempts."
            else:
                return f"Showing steady improvement from {first_result:.0%} to {last_result:.0%}."

        elif trend == "declining":
            return (
                f"Results have declined from {first_result:.0%} to {last_result:.0%}. "
                f"Best result was {best_result:.0%}."
            )

        elif trend == "stable":
            avg_result = sum(r[1] for r in results) / len(results)
            return f"Results have been stable around {avg_result:.0%}."

        else:  # fluctuating
            return (
                f"Results have varied between {min(r[1] for r in results):.0%} "
                f"and {best_result:.0%}."
            )

    async def compare_with_previous(
        self,
        submission_group_id: str,
        current_artifact_id: str,
    ) -> dict[str, Any]:
        """
        Compare current submission with the previous one.

        Args:
            submission_group_id: Submission group ID
            current_artifact_id: Current artifact ID

        Returns:
            Dict with comparison details
        """
        history = await self.get_history(submission_group_id)

        if len(history.attempts) < 2:
            return {"has_previous": False}

        # Find current and previous
        current_idx = None
        for i, attempt in enumerate(history.attempts):
            if attempt.artifact_id == current_artifact_id:
                current_idx = i
                break

        if current_idx is None or current_idx == 0:
            return {"has_previous": False}

        current = history.attempts[current_idx]
        previous = history.attempts[current_idx - 1]

        result_change = None
        if current.result is not None and previous.result is not None:
            result_change = current.result - previous.result

        return {
            "has_previous": True,
            "previous_artifact_id": previous.artifact_id,
            "previous_result": previous.result,
            "current_result": current.result,
            "result_change": result_change,
            "improved": result_change is not None and result_change > 0,
        }
