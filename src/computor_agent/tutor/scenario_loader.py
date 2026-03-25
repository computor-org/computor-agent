"""
Scenario loader for development mode.

Loads a complete test scenario from a directory structure:

    scenario/
    ├── scenario.yaml          # Student info, assignment metadata
    ├── assignment/
    │   └── description.md     # Assignment description (README)
    ├── submission/             # Student's current code (optional)
    │   └── *.py
    ├── reference/              # Reference solution (optional)
    │   └── *.py
    └── test-results.json       # Test output (optional)

Future:
    └── messages/
        └── thread.yaml         # Pre-existing conversation thread
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)


@dataclass
class ScenarioStudent:
    """Student information for the scenario."""
    name: str = "Test Student"


@dataclass
class ScenarioAssignment:
    """Assignment metadata."""
    title: str = "Assignment"
    language: str = "en"


@dataclass
class TestResult:
    """A single test result."""
    name: str
    status: str  # "passed" or "failed"
    message: Optional[str] = None


@dataclass
class TestResults:
    """Parsed test results."""
    total: int = 0
    passed: int = 0
    failed: int = 0
    details: list[TestResult] = field(default_factory=list)

    def format_for_prompt(self) -> str:
        """Format test results for LLM context."""
        lines = [f"Total: {self.total}, Passed: {self.passed}, Failed: {self.failed}"]
        for t in self.details:
            status = "✓" if t.status == "passed" else "✗"
            line = f"  {status} {t.name}"
            if t.message:
                line += f": {t.message}"
            lines.append(line)
        return "\n".join(lines)


@dataclass
class Scenario:
    """A complete dev mode test scenario."""

    # Metadata
    student: ScenarioStudent = field(default_factory=ScenarioStudent)
    assignment: ScenarioAssignment = field(default_factory=ScenarioAssignment)

    # Content
    description: Optional[str] = None
    """Assignment description (from assignment/description.md)."""

    submission_files: dict[str, str] = field(default_factory=dict)
    """Student code: filename -> content."""

    reference_files: dict[str, str] = field(default_factory=dict)
    """Reference solution: filename -> content."""

    test_results: Optional[TestResults] = None
    """Parsed test results."""

    # Source path
    path: Optional[Path] = None


def load_scenario(scenario_dir: Path) -> Scenario:
    """
    Load a scenario from a directory.

    Args:
        scenario_dir: Path to scenario directory (must contain scenario.yaml)

    Returns:
        Loaded Scenario

    Raises:
        ValueError: If scenario directory is invalid
    """
    scenario_dir = Path(scenario_dir)

    if not scenario_dir.is_dir():
        raise ValueError(f"Not a directory: {scenario_dir}")

    # Load scenario.yaml (required)
    yaml_path = scenario_dir / "scenario.yaml"
    if not yaml_path.exists():
        raise ValueError(f"scenario.yaml not found in {scenario_dir}")

    with open(yaml_path) as f:
        data = yaml.safe_load(f) or {}

    # Parse metadata
    student_data = data.get("student", {})
    student = ScenarioStudent(
        name=student_data.get("name", "Test Student"),
    )

    assignment_data = data.get("assignment", {})
    assignment = ScenarioAssignment(
        title=assignment_data.get("title", "Assignment"),
        language=assignment_data.get("language", "en"),
    )

    # Load assignment description
    description = None
    desc_dir = scenario_dir / "assignment"
    if desc_dir.is_dir():
        # Try language-specific first
        for name in [f"description_{assignment.language}.md", "description.md"]:
            desc_path = desc_dir / name
            if desc_path.exists():
                description = desc_path.read_text(encoding="utf-8")
                logger.info(f"Loaded assignment description from {desc_path.name}")
                break

    # Load student submission files
    submission_files = {}
    sub_dir = scenario_dir / "submission"
    if sub_dir.is_dir():
        for f in sorted(sub_dir.rglob("*")):
            if f.is_file() and not f.name.startswith("."):
                rel = str(f.relative_to(sub_dir))
                try:
                    submission_files[rel] = f.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    logger.warning(f"Skipping binary file: {rel}")
        if submission_files:
            logger.info(f"Loaded {len(submission_files)} submission file(s)")

    # Load reference solution files
    reference_files = {}
    ref_dir = scenario_dir / "reference"
    if ref_dir.is_dir():
        for f in sorted(ref_dir.rglob("*")):
            if f.is_file() and not f.name.startswith("."):
                rel = str(f.relative_to(ref_dir))
                try:
                    reference_files[rel] = f.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    logger.warning(f"Skipping binary file: {rel}")
        if reference_files:
            logger.info(f"Loaded {len(reference_files)} reference file(s)")

    # Load test results
    test_results = None
    results_path = scenario_dir / "test-results.json"
    if results_path.exists():
        try:
            raw = json.loads(results_path.read_text(encoding="utf-8"))
            details = [
                TestResult(
                    name=d.get("name", ""),
                    status=d.get("status", "failed"),
                    message=d.get("message"),
                )
                for d in raw.get("details", [])
            ]
            test_results = TestResults(
                total=raw.get("total", len(details)),
                passed=raw.get("passed", sum(1 for d in details if d.status == "passed")),
                failed=raw.get("failed", sum(1 for d in details if d.status == "failed")),
                details=details,
            )
            logger.info(f"Loaded test results: {test_results.passed}/{test_results.total} passed")
        except Exception as e:
            logger.warning(f"Failed to load test results: {e}")

    return Scenario(
        student=student,
        assignment=assignment,
        description=description,
        submission_files=submission_files,
        reference_files=reference_files,
        test_results=test_results,
        path=scenario_dir,
    )
