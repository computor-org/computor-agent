"""
Submission grader module.

Provides automated grading of student submissions using LLM.
"""

import json
import logging
import re
from typing import Callable, Optional, Protocol

from computor_agent.tutor.grading.models import (
    GradingContext,
    GradingResult,
    GradingStatus,
)

logger = logging.getLogger(__name__)


# Prompt for functionality/correctness check
FUNCTIONALITY_CHECK_PROMPT = """Compare the FUNCTIONALITY of these two code implementations.

## Reference Solution (CORRECT):
```
{reference_code}
```

## Student Submission:
```
{student_code}
```

## Task
Carefully compare the student's code to the reference LINE BY LINE. Look for ANY differences that would cause different behavior:
- Different operators (>, <, >=, <=, ==, !=)
- Different logic (and vs or, if vs elif)
- Different calculations or formulas
- Missing or extra conditions
- Different return values
- Different function calls

## Response Format
Respond with JSON:
```json
{{
    "is_functionally_equivalent": <true or false>,
    "differences": ["<difference 1>", "<difference 2>", ...],
    "severity": "<none|minor|major|critical>"
}}
```

- "none": Code is identical or functionally equivalent
- "minor": Small differences that don't affect correctness (variable names, comments)
- "major": Differences that could cause wrong results in some cases
- "critical": Fundamental bugs or completely wrong logic
"""

# Prompt for approach/algorithm check
APPROACH_CHECK_PROMPT = """Compare the APPROACH/ALGORITHM used in these two implementations.

## Assignment Description:
{assignment_description}

## Reference Solution:
```
{reference_code}
```

## Student Submission:
```
{student_code}
```

## Task
Check if the student used the SAME approach as the reference:
- Same algorithm/method
- Same data structures
- Same overall strategy

The reference defines what approach is expected. If the assignment says "use matrix operations" and the reference uses matrix operations, the student must too.

## Response Format
Respond with JSON:
```json
{{
    "same_approach": <true or false>,
    "reference_approach": "<brief description of reference approach>",
    "student_approach": "<brief description of student approach>",
    "issue": "<null or description of wrong approach>"
}}
```
"""

# Prompt for final grading synthesis
GRADING_SYNTHESIS_PROMPT = """You are a grading assistant. Based on the analysis results below, calculate a final grade.

## Analysis Results

### Functionality Check Result:
{functionality_result}

### Approach Check Result:
{approach_result}

## Your Task

Based on the analysis above, determine the final grade using these rules:

**Grade Calculation:**
- Start with 1.0 (100%)
- If NOT functionally equivalent:
  - "critical" severity: subtract 0.5-1.0 (grade becomes 0.0-0.5)
  - "major" severity: subtract 0.3-0.5 (grade becomes 0.5-0.7)
  - "minor" severity: subtract 0.1-0.2 (grade becomes 0.8-0.9)
- If wrong approach (same_approach = false): subtract additional 0.2-0.4

**Status Mapping:**
- grade >= 0.9 AND is_functionally_equivalent = true → "corrected"
- grade < 0.5 → "correction_necessary"
- otherwise → "improvement_possible"

## Required Response

You MUST respond with ONLY a JSON object (no other text):

```json
{{
    "grade": 0.0,
    "status": "correction_necessary",
    "summary": "Brief 1-2 sentence summary of the grading decision.",
    "feedback": "Detailed markdown feedback explaining the issues found.",
    "issues": ["Issue 1", "Issue 2"],
    "suggestions": ["How to fix issue 1", "How to fix issue 2"]
}}
```

NOW generate the JSON response with the actual grade based on the analysis:"""

# Legacy single-prompt template (fallback)
GRADING_PROMPT = """You are an expert programming tutor tasked with grading a student's submission.

{context}

## Grading Instructions

**YOUR TASK**: Compare the student's submission to the reference solution LINE BY LINE.

**CRITICAL**: Look for ANY operator differences (>, <, >=, <=, ==, !=) - these are bugs!

**What to check**:
1. Are all operators the same? (>, <, ==, etc.)
2. Is the logic the same? (and/or, if/elif)
3. Are calculations the same?
4. Are return values the same?

## Status Guidelines

- **CORRECTED**: Code is identical/equivalent to reference. Grade = 1.0
- **CORRECTION_NECESSARY**: Any bug or wrong operator. Grade < 0.5
- **IMPROVEMENT_POSSIBLE**: Works but uses different approach. Grade 0.5-0.89

## Response Format
```json
{{
    "grade": <float between 0.0 and 1.0>,
    "status": "<corrected|correction_necessary|improvement_possible>",
    "summary": "<1-2 sentence summary>",
    "feedback": "<detailed feedback>",
    "issues": ["<issue 1>", ...],
    "suggestions": ["<suggestion 1>", ...]
}}
```
"""


class LLMClient(Protocol):
    """Protocol for LLM client."""

    async def complete(self, prompt: str, max_tokens: int = 2000) -> str:
        """Complete a prompt and return the response."""
        ...


class SubmissionGrader:
    """
    Grades student submissions using LLM.

    Uses a multi-step approach for more accurate grading:
    1. Functionality check - Line-by-line comparison for bugs
    2. Approach check - Algorithm/method comparison
    3. Synthesis - Final grade based on analysis

    Usage:
        grader = SubmissionGrader(llm_client)
        result = await grader.grade(context)
    """

    def __init__(
        self,
        llm: LLMClient,
        prompt_template: Optional[str] = None,
        max_retries: int = 2,
        use_multi_step: bool = True,
    ):
        """
        Initialize the grader.

        Args:
            llm: LLM client for generating grades
            prompt_template: Custom grading prompt template (uses default if None)
            max_retries: Maximum retries for LLM JSON parsing failures
            use_multi_step: Use multi-step grading (default True, more accurate)
        """
        self.llm = llm
        self.prompt_template = prompt_template or GRADING_PROMPT
        self.max_retries = max_retries
        self.use_multi_step = use_multi_step

    async def grade(
        self,
        context: GradingContext,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> GradingResult:
        """
        Grade a student submission.

        Args:
            context: Full grading context with assignment, reference, and submission
            progress_callback: Optional callback to report progress (for multi-step grading)

        Returns:
            GradingResult with grade, status, and feedback
        """
        if self.use_multi_step:
            return await self._grade_multi_step(context, progress_callback)
        else:
            return await self._grade_single_step(context)

    async def _grade_multi_step(
        self,
        context: GradingContext,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> GradingResult:
        """
        Grade using multiple focused LLM calls for better accuracy.

        Steps:
        1. Functionality check - Compare code line by line
        2. Approach check - Compare algorithm/method used
        3. Synthesis - Generate final grade from analysis

        Args:
            context: Grading context with reference and student code
            progress_callback: Optional callback to report progress (step name)
        """
        def report_progress(step: str) -> None:
            if progress_callback:
                progress_callback(step)

        # Get code strings for comparison
        reference_code = "\n\n".join(
            f"# {f.path}\n{f.content}" for f in context.reference_solution
        )
        student_code = "\n\n".join(
            f"# {f.path}\n{f.content}" for f in context.student_submission.files
        )

        # Step 1: Functionality check
        report_progress("Checking functionality (1/3)...")
        logger.debug("Running functionality check...")
        functionality_prompt = FUNCTIONALITY_CHECK_PROMPT.format(
            reference_code=reference_code,
            student_code=student_code,
        )
        functionality_result = await self._call_llm_with_retry(functionality_prompt)
        logger.debug(f"Functionality result: {functionality_result}")

        # Step 2: Approach check
        report_progress("Checking approach (2/3)...")
        logger.debug("Running approach check...")
        approach_prompt = APPROACH_CHECK_PROMPT.format(
            assignment_description=context.assignment_description or "No description provided",
            reference_code=reference_code,
            student_code=student_code,
        )
        approach_result = await self._call_llm_with_retry(approach_prompt)
        logger.debug(f"Approach result: {approach_result}")

        # Step 3: Synthesis
        report_progress("Synthesizing grade (3/3)...")
        logger.debug("Running grading synthesis...")
        synthesis_prompt = GRADING_SYNTHESIS_PROMPT.format(
            functionality_result=functionality_result,
            approach_result=approach_result,
        )
        synthesis_response = await self._call_llm_with_retry(synthesis_prompt)

        # Parse final result
        try:
            return self._parse_response(synthesis_response)
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            logger.warning(f"Failed to parse synthesis response: {e}")
            return GradingResult(
                grade=0.0,
                status=GradingStatus.NOT_REVIEWED,
                feedback="Automatic grading failed. Please review manually.",
                summary="Grading could not be completed automatically.",
            )

    async def _call_llm_with_retry(self, prompt: str) -> str:
        """Call LLM with retry logic for transient failures."""
        for attempt in range(self.max_retries + 1):
            try:
                response = await self.llm.complete(prompt, max_tokens=2000)
                return response
            except Exception as e:
                if attempt < self.max_retries:
                    logger.debug(f"LLM call failed, retrying ({attempt + 1}/{self.max_retries}): {e}")
                    continue
                raise

        return ""  # Should not reach here

    async def _grade_single_step(self, context: GradingContext) -> GradingResult:
        """
        Grade using a single LLM call (legacy approach).

        Less accurate but faster and uses less tokens.
        """
        # Build the prompt
        prompt = self.prompt_template.format(context=context.to_prompt_context())

        # Call LLM with retry logic
        for attempt in range(self.max_retries + 1):
            try:
                response = await self.llm.complete(prompt, max_tokens=2000)
                result = self._parse_response(response)
                return result

            except (json.JSONDecodeError, ValueError, KeyError) as e:
                if attempt < self.max_retries:
                    logger.debug(
                        f"Failed to parse grading response, retrying ({attempt + 1}/{self.max_retries}): {e}"
                    )
                    continue

                logger.warning(f"Failed to parse grading response after {self.max_retries + 1} attempts: {e}")
                # Return a default "needs review" result
                return GradingResult(
                    grade=0.0,
                    status=GradingStatus.NOT_REVIEWED,
                    feedback="Automatic grading failed. Please review manually.",
                    summary="Grading could not be completed automatically.",
                )

            except Exception as e:
                logger.error(f"Grading failed: {e}")
                raise

        # Should not reach here, but just in case
        return GradingResult(
            grade=0.0,
            status=GradingStatus.NOT_REVIEWED,
            feedback="Automatic grading failed. Please review manually.",
            summary="Grading could not be completed automatically.",
        )

    def _parse_response(self, response: str) -> GradingResult:
        """
        Parse the LLM response into a GradingResult.

        Args:
            response: Raw LLM response text

        Returns:
            Parsed GradingResult

        Raises:
            ValueError: If response cannot be parsed
        """
        # Extract JSON from response
        json_str = self._extract_json(response)
        data = json.loads(json_str)

        # Validate and extract fields
        grade = float(data["grade"])
        if not 0.0 <= grade <= 1.0:
            raise ValueError(f"Grade must be between 0.0 and 1.0, got {grade}")

        status_str = data["status"].lower()
        status = GradingStatus.from_string(status_str)

        return GradingResult(
            grade=grade,
            status=status,
            feedback=data.get("feedback", ""),
            summary=data.get("summary", ""),
            issues=data.get("issues", []),
            suggestions=data.get("suggestions", []),
        )

    def _extract_json(self, text: str) -> str:
        """Extract JSON object from text that may contain other content."""
        from computor_agent.tutor.json_utils import extract_json
        return extract_json(text)
