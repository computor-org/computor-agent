"""Reference comparison must actually activate in the messaging flow.

Both halves of the feature existed but were never connected: the production path
passes no local reference path, and the student's submission is downloaded
*after* the context is built — so "do we have both sides?" was always false and
`include_reference_comparison` could not have an effect however it was set.
"""

from pathlib import Path

import pytest

from computor_agent.tutor.config import ContextConfig
from computor_agent.tutor.context import (
    AssignmentInfo,
    CodeContext,
    ConversationContext,
    TriggerType,
)
from computor_agent.tutor.context_builder import ContextBuilder


class FakeReferenceService:
    """Stands in for ReferenceService: records calls, fakes a download."""

    def __init__(self, tmp_path: Path, available: bool = True):
        self.cache_dir = tmp_path / "cache"
        self.available = available
        self.downloads: list[str] = []
        self.compared: list[tuple[dict, dict]] = []

    async def download_reference(self, course_content_id, destination, **kwargs):
        self.downloads.append(str(course_content_id))
        if not self.available:
            return None
        destination = Path(destination)
        destination.mkdir(parents=True, exist_ok=True)
        (destination / "solution.py").write_text("def solve():\n    return 42\n")
        return destination

    def compare_code(self, student_files, reference_files):
        self.compared.append((student_files, reference_files))
        return "a-comparison"


def make_builder(tmp_path: Path, enabled: bool, available: bool = True) -> ContextBuilder:
    builder = ContextBuilder.__new__(ContextBuilder)
    builder.config = ContextConfig(include_reference_comparison=enabled)
    builder.figure_config = None  # figure collection off
    builder.reference_service = FakeReferenceService(tmp_path, available=available)
    return builder


def make_context(with_code: bool = True, course_content_id: str = "cc-1") -> ConversationContext:
    context = ConversationContext(
        trigger_type=TriggerType.MESSAGE,
        submission_group_id="sg-1",
        assignment=AssignmentInfo(course_content_id=course_content_id, title="A1"),
    )
    if with_code:
        context.student_code = CodeContext(
            files={"main.py": "print('hi')\n"}, total_lines=1
        )
    return context


class TestEnsureReferenceComparison:
    async def test_downloads_the_reference_and_produces_a_comparison(self, tmp_path):
        """The regression: in production this produced nothing at all."""
        builder = make_builder(tmp_path, enabled=True)
        context = make_context()

        await builder.ensure_reference_comparison(context)

        assert builder.reference_service.downloads == ["cc-1"]
        assert context.has_reference is True
        assert context.reference_comparison == "a-comparison"
        assert context.has_reference_comparison is True

    async def test_disabled_config_does_nothing(self, tmp_path):
        builder = make_builder(tmp_path, enabled=False)
        context = make_context()

        await builder.ensure_reference_comparison(context)

        assert builder.reference_service.downloads == []
        assert context.reference_comparison is None

    async def test_no_student_code_means_no_download(self, tmp_path):
        """Do not fetch a reference we have nothing to compare against."""
        builder = make_builder(tmp_path, enabled=True)
        context = make_context(with_code=False)

        await builder.ensure_reference_comparison(context)

        assert builder.reference_service.downloads == []
        assert context.reference_comparison is None

    async def test_missing_reference_is_not_an_error(self, tmp_path):
        builder = make_builder(tmp_path, enabled=True, available=False)
        context = make_context()

        await builder.ensure_reference_comparison(context)

        assert builder.reference_service.downloads == ["cc-1"]
        assert context.reference_comparison is None

    async def test_an_existing_reference_is_not_re_downloaded(self, tmp_path):
        """Dev mode passes a local reference path; don't fetch over it."""
        builder = make_builder(tmp_path, enabled=True)
        context = make_context()
        context.reference_code = CodeContext(files={"ref.py": "x = 1\n"}, total_lines=1)

        await builder.ensure_reference_comparison(context)

        assert builder.reference_service.downloads == []
        assert context.reference_comparison == "a-comparison"

    async def test_an_existing_comparison_is_left_alone(self, tmp_path):
        builder = make_builder(tmp_path, enabled=True)
        context = make_context()
        context.reference_comparison = "already-done"

        await builder.ensure_reference_comparison(context)

        assert context.reference_comparison == "already-done"
        assert builder.reference_service.compared == []

    async def test_without_an_assignment_there_is_nothing_to_fetch(self, tmp_path):
        builder = make_builder(tmp_path, enabled=True)
        context = make_context()
        context.assignment = None

        await builder.ensure_reference_comparison(context)

        assert builder.reference_service.downloads == []
        assert context.reference_comparison is None


def test_the_agent_calls_it_after_fetching_the_submission():
    """Order matters: before _ensure_code_context there is no code to diff."""
    import inspect
    from computor_agent.tutor.agent import TutorAgent

    source = inspect.getsource(TutorAgent.process_message)
    assert "ensure_reference_comparison" in source, (
        "the messaging flow must wire the reference comparison in"
    )
    assert source.index("_ensure_code_context") < source.index("ensure_reference_comparison")
