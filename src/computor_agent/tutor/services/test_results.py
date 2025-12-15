"""
Test Results Service for the Tutor AI Agent.

Fetches and parses test result JSON to provide detailed feedback
about which tests passed/failed and why.
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class TestStatus(str, Enum):
    """Status of a test case."""
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    SKIPPED = "skipped"
    PENDING = "pending"


@dataclass
class TestCase:
    """
    A single test case result.

    Attributes:
        name: Name of the test case
        status: Pass/fail/error status
        duration_ms: How long the test took
        message: Error or failure message
        expected: Expected value (for comparison failures)
        actual: Actual value (for comparison failures)
        stack_trace: Full stack trace if available
        file_path: Source file where test is defined
        line_number: Line number in source file
    """
    name: str
    status: TestStatus
    duration_ms: float = 0.0
    message: Optional[str] = None
    expected: Optional[str] = None
    actual: Optional[str] = None
    stack_trace: Optional[str] = None
    file_path: Optional[str] = None
    line_number: Optional[int] = None

    @property
    def is_passed(self) -> bool:
        """Check if test passed."""
        return self.status == TestStatus.PASSED

    @property
    def is_failed(self) -> bool:
        """Check if test failed or errored."""
        return self.status in (TestStatus.FAILED, TestStatus.ERROR)

    def get_failure_summary(self) -> str:
        """Get a concise summary of why the test failed."""
        if self.is_passed:
            return ""

        parts = [f"Test '{self.name}' {self.status.value}"]

        if self.message:
            parts.append(f": {self.message}")

        if self.expected and self.actual:
            parts.append(f"\n  Expected: {self.expected}")
            parts.append(f"\n  Actual: {self.actual}")

        return "".join(parts)


@dataclass
class TestSuite:
    """
    A collection of related test cases.

    Attributes:
        name: Suite name (e.g., class name or file name)
        tests: List of test cases in this suite
        duration_ms: Total suite duration
        setup_error: Error that occurred during setup
        teardown_error: Error that occurred during teardown
    """
    name: str
    tests: list[TestCase] = field(default_factory=list)
    duration_ms: float = 0.0
    setup_error: Optional[str] = None
    teardown_error: Optional[str] = None

    @property
    def passed_count(self) -> int:
        """Number of passed tests."""
        return sum(1 for t in self.tests if t.status == TestStatus.PASSED)

    @property
    def failed_count(self) -> int:
        """Number of failed tests."""
        return sum(1 for t in self.tests if t.status == TestStatus.FAILED)

    @property
    def error_count(self) -> int:
        """Number of errored tests."""
        return sum(1 for t in self.tests if t.status == TestStatus.ERROR)

    @property
    def skipped_count(self) -> int:
        """Number of skipped tests."""
        return sum(1 for t in self.tests if t.status == TestStatus.SKIPPED)

    @property
    def total_count(self) -> int:
        """Total number of tests."""
        return len(self.tests)

    @property
    def pass_rate(self) -> float:
        """Pass rate as a fraction (0.0 to 1.0)."""
        if not self.tests:
            return 0.0
        return self.passed_count / len(self.tests)

    def get_failed_tests(self) -> list[TestCase]:
        """Get all failed and errored tests."""
        return [t for t in self.tests if t.is_failed]


@dataclass
class TestResult:
    """
    Complete test result from a submission.

    Attributes:
        result: Overall result (0.0 to 1.0)
        suites: Test suites with individual test cases
        total_passed: Total passed tests across all suites
        total_failed: Total failed tests across all suites
        total_tests: Total number of tests
        duration_ms: Total test duration
        raw_output: Raw console output from test run
        error_message: Global error message if tests couldn't run
    """
    result: float
    suites: list[TestSuite] = field(default_factory=list)
    total_passed: int = 0
    total_failed: int = 0
    total_tests: int = 0
    duration_ms: float = 0.0
    raw_output: Optional[str] = None
    error_message: Optional[str] = None

    @property
    def pass_rate(self) -> float:
        """Pass rate as a fraction (0.0 to 1.0)."""
        if self.total_tests == 0:
            return self.result
        return self.total_passed / self.total_tests

    @property
    def is_all_passed(self) -> bool:
        """Check if all tests passed."""
        return self.total_failed == 0 and self.total_tests > 0

    def get_all_failed_tests(self) -> list[TestCase]:
        """Get all failed tests across all suites."""
        failed = []
        for suite in self.suites:
            failed.extend(suite.get_failed_tests())
        return failed

    def get_failure_summary(self, max_failures: int = 5) -> str:
        """
        Get a summary of test failures for LLM context.

        Args:
            max_failures: Maximum number of failures to include

        Returns:
            Formatted string describing failures
        """
        if self.is_all_passed:
            return f"All {self.total_tests} tests passed."

        if self.error_message:
            return f"Test execution error: {self.error_message}"

        failed_tests = self.get_all_failed_tests()

        lines = [
            f"Test Results: {self.total_passed}/{self.total_tests} passed "
            f"({self.pass_rate:.1%})"
        ]

        if failed_tests:
            lines.append(f"\nFailed tests ({len(failed_tests)}):")
            for i, test in enumerate(failed_tests[:max_failures]):
                lines.append(f"\n{i+1}. {test.get_failure_summary()}")

            if len(failed_tests) > max_failures:
                lines.append(f"\n... and {len(failed_tests) - max_failures} more failures")

        return "".join(lines)

    def format_for_prompt(self, include_raw_output: bool = False) -> str:
        """
        Format test results for inclusion in LLM prompts.

        Args:
            include_raw_output: Include raw console output

        Returns:
            Formatted string for LLM context
        """
        parts = [
            "=== Test Results ===",
            f"Overall Score: {self.result:.1%}",
            f"Tests: {self.total_passed}/{self.total_tests} passed",
        ]

        if self.duration_ms:
            parts.append(f"Duration: {self.duration_ms:.0f}ms")

        parts.append("")

        # Add suite summaries
        for suite in self.suites:
            parts.append(f"Suite: {suite.name}")
            parts.append(f"  Passed: {suite.passed_count}/{suite.total_count}")

            for test in suite.tests:
                status_icon = "✓" if test.is_passed else "✗"
                parts.append(f"  {status_icon} {test.name}")
                if test.is_failed and test.message:
                    # Truncate long messages
                    msg = test.message[:200] + "..." if len(test.message) > 200 else test.message
                    parts.append(f"      Error: {msg}")

            parts.append("")

        if include_raw_output and self.raw_output:
            parts.append("=== Raw Output ===")
            # Truncate very long output
            output = self.raw_output
            if len(output) > 2000:
                output = output[:2000] + "\n... (truncated)"
            parts.append(output)

        return "\n".join(parts)


class TestResultsService:
    """
    Service for fetching and parsing test results.

    Provides methods to:
    - Fetch test result JSON from API
    - Parse various test result formats (JUnit, pytest, etc.)
    - Format results for LLM context

    Usage:
        service = TestResultsService(client)

        # Get results for an artifact
        result = await service.get_for_artifact(artifact_id)

        # Get results from course content
        result = await service.get_for_course_content(member_id, content_id)

        # Format for LLM
        formatted = result.format_for_prompt()
    """

    def __init__(self, client: Any) -> None:
        """
        Initialize the service.

        Args:
            client: ComputorClient instance
        """
        self.client = client

    async def get_for_artifact(self, artifact_id: str) -> Optional[TestResult]:
        """
        Get test results for a specific artifact.

        Args:
            artifact_id: Submission artifact ID

        Returns:
            TestResult or None if no results available
        """
        try:
            # Fetch artifact with result
            artifact = await self.client.submission_artifacts.get(id=artifact_id)

            if not artifact:
                return None

            # Check for result data
            result_data = getattr(artifact, "latest_result", None)
            if not result_data:
                return None

            return self._parse_result(result_data)

        except Exception as e:
            logger.warning(f"Failed to get test results for artifact {artifact_id}: {e}")
            return None

    async def get_for_course_content(
        self,
        course_member_id: str,
        course_content_id: str,
    ) -> Optional[TestResult]:
        """
        Get test results from tutor course content endpoint.

        Args:
            course_member_id: Course member ID
            course_content_id: Course content ID

        Returns:
            TestResult or None if no results available
        """
        try:
            # Use tutor endpoint to get course content with result
            content = await self.client.tutors.course_members_course_contents_get(
                course_member_id=course_member_id,
                course_content_id=course_content_id,
            )

            if not content:
                return None

            result_data = getattr(content, "result", None)
            if not result_data:
                return None

            return self._parse_result(result_data)

        except Exception as e:
            logger.warning(
                f"Failed to get test results for member {course_member_id}, "
                f"content {course_content_id}: {e}"
            )
            return None

    async def get_for_submission_group(
        self,
        submission_group_id: str,
    ) -> Optional[TestResult]:
        """
        Get test results for a submission group.

        Gets the latest artifact's test results.

        Args:
            submission_group_id: Submission group ID

        Returns:
            TestResult or None if no results available
        """
        try:
            # List artifacts for submission group
            artifacts = await self.client.submission_artifacts.list(
                submission_group_id=submission_group_id,
            )

            if not artifacts:
                return None

            # Sort by upload date, get latest
            sorted_artifacts = sorted(
                artifacts,
                key=lambda a: getattr(a, "uploaded_at", "") or "",
                reverse=True,
            )

            latest = sorted_artifacts[0]
            return await self.get_for_artifact(latest.id)

        except Exception as e:
            logger.warning(
                f"Failed to get test results for submission group {submission_group_id}: {e}"
            )
            return None

    def _parse_result(self, result_data: Any) -> Optional[TestResult]:
        """
        Parse result data into TestResult.

        Handles multiple formats:
        - Direct result object with result_json
        - Result number only
        - Various JSON formats (JUnit, pytest, custom)
        """
        if result_data is None:
            return None

        # Handle dict-like result
        if isinstance(result_data, dict):
            result_value = result_data.get("result", 0.0)
            result_json = result_data.get("result_json")
        else:
            # Handle object with attributes
            result_value = getattr(result_data, "result", 0.0)
            result_json = getattr(result_data, "result_json", None)

        # Ensure result is float
        if isinstance(result_value, (int, float)):
            result_value = float(result_value)
        else:
            result_value = 0.0

        # If no JSON, return basic result
        if not result_json:
            return TestResult(result=result_value)

        # Parse the JSON based on format
        return self._parse_result_json(result_value, result_json)

    def _parse_result_json(
        self,
        result_value: float,
        result_json: Any,
    ) -> TestResult:
        """Parse result JSON into structured TestResult."""

        # Handle string JSON
        if isinstance(result_json, str):
            import json
            try:
                result_json = json.loads(result_json)
            except json.JSONDecodeError:
                return TestResult(
                    result=result_value,
                    raw_output=result_json,
                )

        # Handle different JSON formats
        if isinstance(result_json, dict):
            # Check for JUnit-style format
            if "testsuites" in result_json or "testsuite" in result_json:
                return self._parse_junit_format(result_value, result_json)

            # Check for pytest-style format
            if "tests" in result_json or "summary" in result_json:
                return self._parse_pytest_format(result_value, result_json)

            # Check for custom Computor format
            if "suites" in result_json or "cases" in result_json:
                return self._parse_computor_format(result_value, result_json)

            # Generic format with counts
            return self._parse_generic_format(result_value, result_json)

        # Fallback
        return TestResult(result=result_value)

    def _parse_junit_format(
        self,
        result_value: float,
        data: dict,
    ) -> TestResult:
        """Parse JUnit XML-style JSON format."""
        suites = []
        total_passed = 0
        total_failed = 0
        total_tests = 0

        # Handle single testsuite or multiple testsuites
        testsuites = data.get("testsuites", [data.get("testsuite")])
        if not isinstance(testsuites, list):
            testsuites = [testsuites] if testsuites else []

        for ts in testsuites:
            if not ts:
                continue

            suite_name = ts.get("name", "Unknown Suite")
            suite_tests = []

            testcases = ts.get("testcase", ts.get("testcases", []))
            if not isinstance(testcases, list):
                testcases = [testcases]

            for tc in testcases:
                if not tc:
                    continue

                name = tc.get("name", "Unknown Test")
                time_val = tc.get("time", 0)
                duration = float(time_val) * 1000 if time_val else 0

                # Determine status
                if "failure" in tc:
                    status = TestStatus.FAILED
                    failure = tc["failure"]
                    message = failure.get("message") if isinstance(failure, dict) else str(failure)
                    total_failed += 1
                elif "error" in tc:
                    status = TestStatus.ERROR
                    error = tc["error"]
                    message = error.get("message") if isinstance(error, dict) else str(error)
                    total_failed += 1
                elif "skipped" in tc:
                    status = TestStatus.SKIPPED
                    message = None
                else:
                    status = TestStatus.PASSED
                    message = None
                    total_passed += 1

                total_tests += 1

                suite_tests.append(TestCase(
                    name=name,
                    status=status,
                    duration_ms=duration,
                    message=message,
                    file_path=tc.get("classname"),
                ))

            suites.append(TestSuite(
                name=suite_name,
                tests=suite_tests,
                duration_ms=float(ts.get("time", 0)) * 1000,
            ))

        return TestResult(
            result=result_value,
            suites=suites,
            total_passed=total_passed,
            total_failed=total_failed,
            total_tests=total_tests,
        )

    def _parse_pytest_format(
        self,
        result_value: float,
        data: dict,
    ) -> TestResult:
        """Parse pytest JSON format."""
        tests = data.get("tests", [])
        summary = data.get("summary", {})

        suites_map: dict[str, list[TestCase]] = {}

        for test in tests:
            nodeid = test.get("nodeid", "")
            # Extract suite name from nodeid (e.g., "test_file.py::TestClass::test_method")
            parts = nodeid.split("::")
            suite_name = parts[0] if parts else "Unknown"
            test_name = parts[-1] if len(parts) > 1 else nodeid

            outcome = test.get("outcome", "")
            if outcome == "passed":
                status = TestStatus.PASSED
            elif outcome == "failed":
                status = TestStatus.FAILED
            elif outcome == "error":
                status = TestStatus.ERROR
            elif outcome == "skipped":
                status = TestStatus.SKIPPED
            else:
                status = TestStatus.PENDING

            # Extract failure info
            message = None
            longrepr = test.get("longrepr")
            if longrepr:
                if isinstance(longrepr, dict):
                    message = longrepr.get("reprcrash", {}).get("message")
                else:
                    message = str(longrepr)[:500]  # Truncate long messages

            test_case = TestCase(
                name=test_name,
                status=status,
                duration_ms=test.get("duration", 0) * 1000,
                message=message,
                file_path=test.get("path"),
                line_number=test.get("lineno"),
            )

            if suite_name not in suites_map:
                suites_map[suite_name] = []
            suites_map[suite_name].append(test_case)

        suites = [
            TestSuite(name=name, tests=tests)
            for name, tests in suites_map.items()
        ]

        return TestResult(
            result=result_value,
            suites=suites,
            total_passed=summary.get("passed", 0),
            total_failed=summary.get("failed", 0) + summary.get("error", 0),
            total_tests=summary.get("total", len(tests)),
            duration_ms=summary.get("duration", 0) * 1000,
        )

    def _parse_computor_format(
        self,
        result_value: float,
        data: dict,
    ) -> TestResult:
        """Parse Computor's custom format."""
        suites = []
        total_passed = 0
        total_failed = 0
        total_tests = 0

        for suite_data in data.get("suites", []):
            suite_tests = []

            for case in suite_data.get("cases", []):
                status_str = case.get("status", "").lower()
                status = TestStatus.PASSED
                if status_str in ("failed", "failure"):
                    status = TestStatus.FAILED
                elif status_str == "error":
                    status = TestStatus.ERROR
                elif status_str == "skipped":
                    status = TestStatus.SKIPPED

                test_case = TestCase(
                    name=case.get("name", "Unknown"),
                    status=status,
                    duration_ms=case.get("duration_ms", 0),
                    message=case.get("message"),
                    expected=case.get("expected"),
                    actual=case.get("actual"),
                    stack_trace=case.get("stack_trace"),
                )

                suite_tests.append(test_case)
                total_tests += 1
                if status == TestStatus.PASSED:
                    total_passed += 1
                elif status in (TestStatus.FAILED, TestStatus.ERROR):
                    total_failed += 1

            suites.append(TestSuite(
                name=suite_data.get("name", "Unknown Suite"),
                tests=suite_tests,
                duration_ms=suite_data.get("duration_ms", 0),
            ))

        return TestResult(
            result=result_value,
            suites=suites,
            total_passed=total_passed,
            total_failed=total_failed,
            total_tests=total_tests,
            duration_ms=data.get("duration_ms", 0),
            raw_output=data.get("output"),
            error_message=data.get("error"),
        )

    def _parse_generic_format(
        self,
        result_value: float,
        data: dict,
    ) -> TestResult:
        """Parse generic format with basic counts."""
        return TestResult(
            result=result_value,
            total_passed=data.get("passed", data.get("pass", 0)),
            total_failed=data.get("failed", data.get("fail", 0)),
            total_tests=data.get("total", data.get("tests", 0)),
            duration_ms=data.get("duration", data.get("time", 0)) * 1000,
            raw_output=data.get("output", data.get("stdout")),
            error_message=data.get("error", data.get("stderr")),
        )
