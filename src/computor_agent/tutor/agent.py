"""
Tutor Agent orchestrator for the Computor Agent.

This is the main entry point for tutor functionality. It:
1. Builds context from API data
2. Runs security checks
3. Classifies intent
4. Executes the appropriate strategy
5. Returns the response

Note: The agent does NOT schedule itself. A separate scheduler
should call process_message() or process_submission() when needed.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Protocol

from computor_agent.tutor.config import TutorConfig
from computor_agent.tutor.context import ConversationContext
from computor_agent.tutor.context_builder import ContextBuilder
from computor_agent.tutor.intents import Intent, IntentClassification, IntentClassifier
from computor_agent.tutor.security import SecurityCheckResult, SecurityGate
from computor_agent.tutor.strategies import StrategyRegistry, StrategyResponse

logger = logging.getLogger(__name__)


class LLMClient(Protocol):
    """Protocol for LLM client used by TutorAgent."""

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


class ComputorClientProtocol(Protocol):
    """Protocol for the Computor API client."""

    async def get_submission_group(self, submission_group_id: str) -> dict:
        """Get submission group details."""
        ...

    async def get_messages(self, submission_group_id: str) -> list[dict]:
        """Get messages for a submission group."""
        ...

    async def get_course_member_comments(self, course_member_id: str) -> list[dict]:
        """Get comments for a course member."""
        ...

    async def get_course_content(self, course_content_id: str) -> dict:
        """Get course content (assignment) details."""
        ...

    async def get_course_members(self, submission_group_id: str) -> list[dict]:
        """Get course members for a submission group."""
        ...

    async def create_message(
        self,
        submission_group_id: str,
        content: str,
        title: str = "",
    ) -> dict:
        """Create a message in a submission group."""
        ...

    async def update_submission_grading(
        self,
        submission_group_id: str,
        status: int,
        grade: Optional[float] = None,
        comment: Optional[str] = None,
    ) -> dict:
        """Update grading for a submission."""
        ...


@dataclass
class ProcessingResult:
    """
    Result of processing a student interaction.

    Contains all information about what happened during processing.
    """

    success: bool
    """Whether processing completed successfully."""

    message_sent: bool
    """Whether a response message was sent."""

    response: Optional[StrategyResponse] = None
    """The strategy response (if generated)."""

    intent: Optional[IntentClassification] = None
    """The classified intent (if classification ran)."""

    security_result: Optional[SecurityCheckResult] = None
    """Security check result (if check ran)."""

    blocked_by_security: bool = False
    """Whether response was blocked by security."""

    error: Optional[str] = None
    """Error message if processing failed."""

    processing_time_ms: float = 0.0
    """Total processing time in milliseconds."""

    context_id: Optional[str] = None
    """ID of the context used for processing."""


class TutorAgent:
    """
    Main tutor agent orchestrator.

    Coordinates:
    - Context building
    - Security checking
    - Intent classification
    - Strategy execution
    - Response delivery

    The agent is stateless - each call processes a single interaction
    with a fresh context that is destroyed after use.

    Usage:
        agent = TutorAgent(
            config=config,
            llm=llm_client,
            client=computor_client,
        )

        # Process a message
        result = await agent.process_message(
            submission_group_id="...",
            message={...},
            repository_path=Path("/path/to/repo"),
        )

        if result.success and not result.blocked_by_security:
            # Message was sent to student
            pass
    """

    def __init__(
        self,
        config: TutorConfig,
        llm: LLMClient,
        client: ComputorClientProtocol,
    ) -> None:
        """
        Initialize the tutor agent.

        Args:
            config: Complete tutor configuration
            llm: LLM client for all AI operations
            client: Computor API client
        """
        self.config = config
        self.llm = llm
        self.client = client

        # Initialize components
        self.context_builder = ContextBuilder(client, config.context)
        self.security_gate = SecurityGate(config.security, llm)
        self.intent_classifier = IntentClassifier(llm)
        self.strategy_registry = StrategyRegistry(
            config.personality,
            config.grading,
        )

    async def process_message(
        self,
        submission_group_id: str,
        message: dict,
        repository_path: Optional[Path] = None,
        reference_path: Optional[Path] = None,
        send_response: bool = True,
    ) -> ProcessingResult:
        """
        Process a student message and generate a response.

        Args:
            submission_group_id: The submission group ID
            message: The message dict that triggered this
            repository_path: Path to student's cloned repository
            reference_path: Path to reference solution (if enabled)
            send_response: Whether to send the response via API

        Returns:
            ProcessingResult with all processing information
        """
        import time

        start_time = time.perf_counter()
        context_id = str(uuid.uuid4())

        context: Optional[ConversationContext] = None

        try:
            # Build context
            context = await self.context_builder.build_for_message(
                submission_group_id=submission_group_id,
                message=message,
                repository_path=repository_path,
                reference_path=reference_path,
            )
            context.context_id = context_id

            # Run security check
            security_result = await self.security_gate.check(context)

            if not security_result.is_safe and self.config.security.block_on_threat:
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                return ProcessingResult(
                    success=True,
                    message_sent=False,
                    security_result=security_result,
                    blocked_by_security=True,
                    processing_time_ms=elapsed_ms,
                    context_id=context_id,
                )

            # Classify intent
            intent = await self.intent_classifier.classify(context)

            # Get strategy for intent
            strategy = self.strategy_registry.get(intent.intent)

            # Get strategy config
            strategy_config = self._get_strategy_config(intent.intent)

            # Check if strategy is enabled
            if not strategy_config.enabled:
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                return ProcessingResult(
                    success=True,
                    message_sent=False,
                    intent=intent,
                    security_result=security_result,
                    error=f"Strategy {intent.intent.value} is disabled",
                    processing_time_ms=elapsed_ms,
                    context_id=context_id,
                )

            # Execute strategy
            response = await strategy.execute(context, self.llm, strategy_config)

            # Send response if configured
            message_sent = False
            if send_response and response.message_content:
                await self.client.create_message(
                    submission_group_id=submission_group_id,
                    content=response.message_content,
                    title=response.message_title or "",
                )
                message_sent = True

            elapsed_ms = (time.perf_counter() - start_time) * 1000

            return ProcessingResult(
                success=True,
                message_sent=message_sent,
                response=response,
                intent=intent,
                security_result=security_result,
                processing_time_ms=elapsed_ms,
                context_id=context_id,
            )

        except Exception as e:
            logger.exception(f"Error processing message: {e}")
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            return ProcessingResult(
                success=False,
                message_sent=False,
                error=str(e),
                processing_time_ms=elapsed_ms,
                context_id=context_id,
            )

        finally:
            # Always destroy context
            if context:
                context.destroy()

    async def process_submission(
        self,
        submission_group_id: str,
        artifact: dict,
        repository_path: Optional[Path] = None,
        reference_path: Optional[Path] = None,
        send_response: bool = True,
        submit_grade: bool = False,
    ) -> ProcessingResult:
        """
        Process a submission (artifact with submit=True) and generate a review.

        Args:
            submission_group_id: The submission group ID
            artifact: The submission artifact dict that triggered this
            repository_path: Path to student's cloned repository
            reference_path: Path to reference solution (if enabled)
            send_response: Whether to send the review message via API
            submit_grade: Whether to submit the grade via API

        Returns:
            ProcessingResult with all processing information
        """
        import time

        start_time = time.perf_counter()
        context_id = str(uuid.uuid4())

        context: Optional[ConversationContext] = None

        try:
            # Build context
            context = await self.context_builder.build_for_submission(
                submission_group_id=submission_group_id,
                artifact=artifact,
                repository_path=repository_path,
                reference_path=reference_path,
            )
            context.context_id = context_id

            # Run security check
            security_result = await self.security_gate.check(context)

            if not security_result.is_safe and self.config.security.block_on_threat:
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                return ProcessingResult(
                    success=True,
                    message_sent=False,
                    security_result=security_result,
                    blocked_by_security=True,
                    processing_time_ms=elapsed_ms,
                    context_id=context_id,
                )

            # For submissions, intent is always SUBMISSION_REVIEW
            intent = IntentClassification(
                intent=Intent.SUBMISSION_REVIEW,
                confidence=1.0,
                reasoning="Triggered by submission artifact",
            )

            # Get submission review strategy
            strategy = self.strategy_registry.get(Intent.SUBMISSION_REVIEW)
            strategy_config = self._get_strategy_config(Intent.SUBMISSION_REVIEW)

            if not strategy_config.enabled:
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                return ProcessingResult(
                    success=True,
                    message_sent=False,
                    intent=intent,
                    security_result=security_result,
                    error="Submission review strategy is disabled",
                    processing_time_ms=elapsed_ms,
                    context_id=context_id,
                )

            # Execute strategy
            response = await strategy.execute(context, self.llm, strategy_config)

            # Send response if configured
            message_sent = False
            if send_response and response.message_content:
                await self.client.create_message(
                    submission_group_id=submission_group_id,
                    content=response.message_content,
                    title=response.message_title or "Submission Review",
                )
                message_sent = True

            # Submit grade if configured and available
            if (
                submit_grade
                and self.config.grading.enabled
                and self.config.grading.auto_submit_grade
                and response.grade is not None
            ):
                await self.client.update_submission_grading(
                    submission_group_id=submission_group_id,
                    status=response.grade_status or self.config.grading.default_status,
                    grade=response.grade,
                    comment=response.grade_comment,
                )

            elapsed_ms = (time.perf_counter() - start_time) * 1000

            return ProcessingResult(
                success=True,
                message_sent=message_sent,
                response=response,
                intent=intent,
                security_result=security_result,
                processing_time_ms=elapsed_ms,
                context_id=context_id,
            )

        except Exception as e:
            logger.exception(f"Error processing submission: {e}")
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            return ProcessingResult(
                success=False,
                message_sent=False,
                error=str(e),
                processing_time_ms=elapsed_ms,
                context_id=context_id,
            )

        finally:
            # Always destroy context
            if context:
                context.destroy()

    def _get_strategy_config(self, intent: Intent):
        """Get the strategy config for an intent."""
        config_map = {
            Intent.QUESTION_EXAMPLE: self.config.strategies.question_example,
            Intent.QUESTION_HOWTO: self.config.strategies.question_howto,
            Intent.HELP_DEBUG: self.config.strategies.help_debug,
            Intent.HELP_REVIEW: self.config.strategies.help_review,
            Intent.SUBMISSION_REVIEW: self.config.strategies.submission_review,
            Intent.CLARIFICATION: self.config.strategies.clarification,
            Intent.OTHER: self.config.strategies.other,
        }
        return config_map.get(intent, self.config.strategies.other)

    async def check_security_only(
        self,
        submission_group_id: str,
        message: dict,
        repository_path: Optional[Path] = None,
    ) -> SecurityCheckResult:
        """
        Run only the security check without generating a response.

        Useful for pre-screening content.

        Args:
            submission_group_id: The submission group ID
            message: The message dict to check
            repository_path: Path to student's repository

        Returns:
            SecurityCheckResult
        """
        context = await self.context_builder.build_for_message(
            submission_group_id=submission_group_id,
            message=message,
            repository_path=repository_path,
        )

        try:
            return await self.security_gate.check(context)
        finally:
            context.destroy()

    async def classify_only(
        self,
        submission_group_id: str,
        message: dict,
    ) -> IntentClassification:
        """
        Run only intent classification without generating a response.

        Useful for analytics or routing.

        Args:
            submission_group_id: The submission group ID
            message: The message dict to classify

        Returns:
            IntentClassification
        """
        context = await self.context_builder.build_for_message(
            submission_group_id=submission_group_id,
            message=message,
        )

        try:
            return await self.intent_classifier.classify(context)
        finally:
            context.destroy()
