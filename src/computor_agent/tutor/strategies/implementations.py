"""
Concrete strategy implementations for the Tutor AI Agent.

Each strategy handles a specific intent and generates appropriate responses.
"""

from typing import TYPE_CHECKING, Protocol

from computor_agent.tutor.intents.types import Intent
from computor_agent.tutor.prompts.templates import PERSONALITY_PROMPTS, STRATEGY_PROMPTS
from computor_agent.tutor.strategies.base import BaseStrategy, StrategyResponse

if TYPE_CHECKING:
    from computor_agent.tutor.config import PersonalityConfig, StrategyConfig
    from computor_agent.tutor.context import ConversationContext


class LLMClient(Protocol):
    """Protocol for LLM client used by strategies."""

    async def complete(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        max_tokens: int = 1000,
        temperature: float = 0.7,
    ) -> str:
        """Generate a completion for the given prompt."""
        ...


class BaseStrategyImpl(BaseStrategy):
    """
    Base implementation with common functionality.

    Subclasses should set:
    - name: Strategy identifier
    - intent: The Intent this strategy handles
    - prompt_key: Key in STRATEGY_PROMPTS dict
    """

    name: str = "base"
    intent: Intent = Intent.OTHER
    prompt_key: str = "other"

    def __init__(self, personality_config: "PersonalityConfig") -> None:
        """
        Initialize the strategy.

        Args:
            personality_config: Personality configuration for prompts
        """
        self.personality_config = personality_config

    def get_personality_prompt(self) -> str:
        """Get the personality prompt based on config."""
        tone = self.personality_config.tone.value
        prompt = PERSONALITY_PROMPTS.get(tone, PERSONALITY_PROMPTS["friendly_professional"])
        return prompt.format(tutor_name=self.personality_config.name)

    def build_system_prompt(
        self,
        context: "ConversationContext",
        config: "StrategyConfig",
    ) -> str:
        """Build system prompt using template and context."""
        template = STRATEGY_PROMPTS.get(self.prompt_key, STRATEGY_PROMPTS["other"])

        # Gather template variables
        variables = {
            "personality_prompt": self.get_personality_prompt(),
            "language": self.personality_config.language,
            "assignment_description": self._get_assignment_description(context),
            "student_code": context.get_formatted_code() if context.has_code else "(No code available)",
            "previous_messages": context.get_formatted_previous_messages(),
            "reference_solution_section": self._get_reference_section(context),
            "grading_instructions": "",  # Set by submission strategy
            # Enhanced context sections
            "test_results_section": self._get_test_results_section(context),
            "submission_history_section": self._get_submission_history_section(context),
            "reference_comparison_section": self._get_reference_comparison_section(context),
            "student_progress_section": self._get_student_progress_section(context),
        }

        # Apply custom prefix/suffix
        base_prompt = template.format(**variables)

        if self.personality_config.custom_system_prompt_prefix:
            base_prompt = f"{self.personality_config.custom_system_prompt_prefix}\n\n{base_prompt}"

        if self.personality_config.custom_system_prompt_suffix:
            base_prompt = f"{base_prompt}\n\n{self.personality_config.custom_system_prompt_suffix}"

        return base_prompt

    def build_user_message(self, context: "ConversationContext") -> str:
        """Build user message from context."""
        if context.trigger_message:
            return context.trigger_message.content
        return "(No message)"

    async def execute(
        self,
        context: "ConversationContext",
        llm: LLMClient,
        config: "StrategyConfig",
    ) -> StrategyResponse:
        """Execute the strategy."""
        system_prompt = self.build_system_prompt(context, config)
        user_message = self.build_user_message(context)

        response = await llm.complete(
            prompt=user_message,
            system_prompt=system_prompt,
            max_tokens=config.max_response_tokens,
            temperature=config.temperature,
        )

        return StrategyResponse(
            message_content=response,
            strategy_name=self.name,
        )

    def _get_assignment_description(self, context: "ConversationContext") -> str:
        """Get assignment description from context."""
        if context.assignment:
            parts = []
            if context.assignment.title:
                parts.append(f"Title: {context.assignment.title}")
            if context.assignment.description:
                parts.append(context.assignment.description)
            return "\n".join(parts) if parts else "(No assignment description)"
        return "(No assignment description)"

    def _get_reference_section(self, context: "ConversationContext") -> str:
        """Get reference solution section if available."""
        if not context.has_reference:
            return ""

        code = context.reference_code.files
        formatted = []
        for file_path, content in code.items():
            formatted.append(f"=== {file_path} ===\n{content}")

        return f"""Reference Solution:
---
{chr(10).join(formatted)}
---"""

    def _get_test_results_section(self, context: "ConversationContext") -> str:
        """Get test results section if available."""
        if not context.has_test_results:
            return ""

        return f"""
Test Results:
---
{context.test_results.format_for_prompt()}
---"""

    def _get_submission_history_section(self, context: "ConversationContext") -> str:
        """Get submission history section if available."""
        if not context.has_submission_history:
            return ""

        return f"""
Submission History:
---
{context.submission_history.format_for_prompt()}
---"""

    def _get_reference_comparison_section(self, context: "ConversationContext") -> str:
        """Get reference comparison section if available."""
        if not context.has_reference_comparison:
            return ""

        return f"""
Reference Comparison:
---
{context.reference_comparison.format_for_prompt(max_diffs=3, max_lines_per_diff=30)}
---"""

    def _get_student_progress_section(self, context: "ConversationContext") -> str:
        """Get student progress section if available."""
        if not context.has_student_progress:
            return ""

        return f"""
Student Progress:
---
{context.student_progress.format_for_prompt()}
---"""


class QuestionExampleStrategy(BaseStrategyImpl):
    """Strategy for questions about the assignment/example."""

    name = "question_example"
    intent = Intent.QUESTION_EXAMPLE
    prompt_key = "question_example"


class QuestionHowtoStrategy(BaseStrategyImpl):
    """Strategy for general how-to questions."""

    name = "question_howto"
    intent = Intent.QUESTION_HOWTO
    prompt_key = "question_howto"


class HelpDebugStrategy(BaseStrategyImpl):
    """Strategy for debugging help requests."""

    name = "help_debug"
    intent = Intent.HELP_DEBUG
    prompt_key = "help_debug"

    def build_user_message(self, context: "ConversationContext") -> str:
        """Include any error messages or symptoms with the message."""
        parts = []

        if context.trigger_message:
            parts.append(f"Student's question:\n{context.trigger_message.content}")

        # Look for error information in the message
        if context.student_notes:
            parts.append(f"\nNotes about this student:\n{context.student_notes}")

        return "\n\n".join(parts) if parts else "(No message)"


class HelpReviewStrategy(BaseStrategyImpl):
    """Strategy for code review requests."""

    name = "help_review"
    intent = Intent.HELP_REVIEW
    prompt_key = "help_review"


class SubmissionReviewStrategy(BaseStrategyImpl):
    """Strategy for official submission reviews."""

    name = "submission_review"
    intent = Intent.SUBMISSION_REVIEW
    prompt_key = "submission_review"

    def __init__(
        self,
        personality_config: "PersonalityConfig",
        grading_enabled: bool = False,
    ) -> None:
        """
        Initialize submission review strategy.

        Args:
            personality_config: Personality configuration
            grading_enabled: Whether to include grading instructions
        """
        super().__init__(personality_config)
        self.grading_enabled = grading_enabled

    def build_system_prompt(
        self,
        context: "ConversationContext",
        config: "StrategyConfig",
    ) -> str:
        """Build system prompt with grading instructions if enabled."""
        template = STRATEGY_PROMPTS["submission_review"]

        grading_instructions = ""
        if self.grading_enabled:
            grading_instructions = """
After your review, provide a grade assessment:
- grade: float from 0.0 to 1.0 (0 = fail, 1 = perfect)
- status: 0 (not reviewed), 1 (correct), 2 (needs correction), 3 (could be improved)

Format at the end of your response:
---GRADING---
grade: <value>
status: <value>
---END GRADING---"""

        variables = {
            "personality_prompt": self.get_personality_prompt(),
            "language": self.personality_config.language,
            "assignment_description": self._get_assignment_description(context),
            "student_code": context.get_formatted_code() if context.has_code else "(No code available)",
            "reference_solution_section": self._get_reference_section(context),
            "grading_instructions": grading_instructions,
            # Enhanced context sections
            "test_results_section": self._get_test_results_section(context),
            "submission_history_section": self._get_submission_history_section(context),
            "reference_comparison_section": self._get_reference_comparison_section(context),
            "student_progress_section": self._get_student_progress_section(context),
        }

        base_prompt = template.format(**variables)

        if self.personality_config.custom_system_prompt_prefix:
            base_prompt = f"{self.personality_config.custom_system_prompt_prefix}\n\n{base_prompt}"

        if self.personality_config.custom_system_prompt_suffix:
            base_prompt = f"{base_prompt}\n\n{self.personality_config.custom_system_prompt_suffix}"

        return base_prompt

    def build_user_message(self, context: "ConversationContext") -> str:
        """Build message for submission review."""
        parts = ["Please review this submission."]

        if context.trigger_message:
            parts.append(f"\nStudent's note:\n{context.trigger_message.content}")

        if context.student_notes:
            parts.append(f"\nNotes about this student:\n{context.student_notes}")

        return "\n".join(parts)

    async def execute(
        self,
        context: "ConversationContext",
        llm: LLMClient,
        config: "StrategyConfig",
    ) -> StrategyResponse:
        """Execute with optional grading extraction."""
        response = await super().execute(context, llm, config)

        if self.grading_enabled:
            # Try to extract grading from response
            grade, status = self._extract_grading(response.message_content)
            response.grade = grade
            response.grade_status = status

            # Remove grading block from message content
            response.message_content = self._remove_grading_block(response.message_content)

        return response

    def _extract_grading(self, content: str) -> tuple[float | None, int | None]:
        """Extract grading information from response."""
        import re

        grade = None
        status = None

        # Look for grading block
        grading_match = re.search(
            r"---GRADING---\s*\n"
            r"grade:\s*([\d.]+)\s*\n"
            r"status:\s*(\d)\s*\n"
            r"---END GRADING---",
            content,
            re.IGNORECASE,
        )

        if grading_match:
            try:
                grade = float(grading_match.group(1))
                grade = max(0.0, min(1.0, grade))  # Clamp to 0-1
            except ValueError:
                pass

            try:
                status = int(grading_match.group(2))
                status = max(0, min(3, status))  # Clamp to 0-3
            except ValueError:
                pass

        return grade, status

    def _remove_grading_block(self, content: str) -> str:
        """Remove grading block from content."""
        import re

        return re.sub(
            r"\n*---GRADING---.*?---END GRADING---\n*",
            "",
            content,
            flags=re.DOTALL | re.IGNORECASE,
        ).strip()


class ClarificationStrategy(BaseStrategyImpl):
    """Strategy for follow-up clarification questions."""

    name = "clarification"
    intent = Intent.CLARIFICATION
    prompt_key = "clarification"


class OtherStrategy(BaseStrategyImpl):
    """Fallback strategy for unclear or off-topic messages."""

    name = "other"
    intent = Intent.OTHER
    prompt_key = "other"
