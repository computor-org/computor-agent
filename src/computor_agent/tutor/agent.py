"""
Tutor Agent orchestrator for the Computor Agent.

This is the main entry point for tutor functionality. It:
1. Builds context from API data
2. Runs security checks
3. Classifies intent
4. Executes the appropriate strategy
5. Returns the response

Note: The agent does NOT schedule itself. A separate scheduler
should call process_message() when triggered.

Uses ComputorClient from computor-client package directly.
"""

import logging
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Protocol

# Import API types from computor-types (source of truth)
from computor_types.student_course_contents import CourseContentStudentGet

from computor_agent.tutor.config import TutorConfig
from computor_agent.tutor.context import ConversationContext
from computor_agent.tutor.context_builder import ContextBuilder
from computor_agent.tutor.intents import IntentClassification, IntentClassifier
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

    response_message_id: Optional[str] = None
    """ID of the response message that was created (if sent)."""


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

    Uses ComputorClient from computor-client package directly.

    Usage:
        from computor_client import ComputorClient

        async with ComputorClient(base_url=url) as client:
            await client.login(username=user, password=password)

            agent = TutorAgent(
                config=config,
                llm=llm_client,
                client=client,
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
        client: Any,  # ComputorClient from computor-client
    ) -> None:
        """
        Initialize the tutor agent.

        Args:
            config: Complete tutor configuration
            llm: LLM client for all AI operations
            client: ComputorClient instance from computor-client package
        """
        self.config = config
        self.llm = llm
        self.client = client

        # Initialize components
        self.context_builder = ContextBuilder(client, config.context)
        self.security_gate = SecurityGate(config.security, llm)
        self.intent_classifier = IntentClassifier(llm)
        self.strategy_registry = StrategyRegistry(config.personality)

    async def process_message(
        self,
        submission_group_id: str,
        message: dict,
        repository_path: Optional[Path] = None,
        reference_path: Optional[Path] = None,
        send_response: bool = True,
        reply_to_message_id: Optional[str] = None,
        course_content: Optional[CourseContentStudentGet] = None,
        course_member_id: Optional[str] = None,
        assignment_context: Optional["AssignmentContext"] = None,
    ) -> ProcessingResult:
        """
        Process a student message and generate a response.

        Args:
            submission_group_id: The submission group ID
            message: The message dict that triggered this
            repository_path: Path to student's cloned repository
            reference_path: Path to reference solution (if enabled)
            send_response: Whether to send the response via API
            reply_to_message_id: ID of message to reply to (creates message chain)
            course_content: Pre-fetched CourseContentStudentGet to avoid redundant API calls
            course_member_id: Course member ID (for efficient data extraction)
            assignment_context: Assignment context from dev mode (for assignment description)

        Returns:
            ProcessingResult with all processing information
        """
        import time

        start_time = time.perf_counter()
        context_id = str(uuid.uuid4())

        context: Optional[ConversationContext] = None

        try:
            # Build context (use pre-fetched course_content if available)
            context = await self.context_builder.build_for_message(
                submission_group_id=submission_group_id,
                message=message,
                repository_path=repository_path,
                reference_path=reference_path,
                course_content=course_content,
                course_member_id=course_member_id,
                assignment_context=assignment_context,
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
            classification = await self.intent_classifier.classify(context)

            # Check if we need to download submission code for code-related intents
            # Skip in dev mode (assignment_context set) - no real API to download from
            if not assignment_context:
                await self._ensure_code_context(context, classification)

            # Get strategy for classification (handles None intent with fallback)
            strategy = self.strategy_registry.get_strategy(classification)

            # Get strategy config
            strategy_config = self._get_strategy_config(classification.intent)

            # Check if strategy is enabled
            if not strategy_config.enabled:
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                intent_name = classification.intent.value if classification.intent else "fallback"
                return ProcessingResult(
                    success=True,
                    message_sent=False,
                    intent=classification,
                    security_result=security_result,
                    error=f"Strategy {intent_name} is disabled",
                    processing_time_ms=elapsed_ms,
                    context_id=context_id,
                )

            # Execute strategy with classification
            response = await strategy.execute(context, classification, self.llm, strategy_config)

            # Send response if configured
            message_sent = False
            response_message_id = None
            if send_response and response.message_content:
                # Add response tag to title for trigger detection
                formatted_title = self._format_response_title(response.message_title)

                # Reply to the triggering message to create a chain
                parent_id = reply_to_message_id or message.get("id")
                logger.debug(f"reply_to_message_id={reply_to_message_id}, message.get('id')={message.get('id')}, parent_id={parent_id}")

                # Use ComputorClient.messages.create() directly
                # When replying (parent_id set), don't set target - it's inherited from parent
                # Only set submission_group_id for new threads
                message_data: dict[str, Any] = {
                    "content": response.message_content,
                    "title": formatted_title,
                }
                if parent_id:
                    message_data["parent_id"] = parent_id
                    logger.debug(f"Using parent_id for reply: {parent_id}")
                else:
                    # New message thread - must specify target
                    message_data["submission_group_id"] = submission_group_id
                    logger.debug(f"New thread, using submission_group_id: {submission_group_id}")

                logger.info(f"Creating message with data: {message_data}")
                created_message = await self.client.messages.create(data=message_data)
                message_sent = True
                response_message_id = created_message.id

            # Mark the original message as read to prevent re-processing
            message_id = message.get("id")
            if message_id:
                try:
                    await self.client.messages.reads(id=message_id)
                except Exception as e:
                    logger.warning(f"Failed to mark message {message_id} as read: {e}")

            elapsed_ms = (time.perf_counter() - start_time) * 1000

            return ProcessingResult(
                success=True,
                message_sent=message_sent,
                response=response,
                intent=classification,
                security_result=security_result,
                processing_time_ms=elapsed_ms,
                context_id=context_id,
                response_message_id=response_message_id,
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

    def _format_response_title(self, title: Optional[str], default: str = "") -> str:
        """
        Format the response title with the configured response tag.

        Adds the response tag (e.g., #ai::response) to the title so the
        trigger checker can identify messages sent by the agent.

        Args:
            title: Original title (can be None or empty)
            default: Default title if none provided

        Returns:
            Title with response tag prepended
        """
        response_tag = str(self.config.triggers.response_tag)  # e.g., "#ai::response"
        base_title = title or default
        if base_title:
            return f"{response_tag} {base_title}"
        return response_tag

    def _get_strategy_config(self, intent: Optional["Intent"]):
        """Get the strategy config for an intent (None returns fallback config)."""
        from computor_agent.tutor.intents import Intent

        if intent is None:
            return self.config.strategies.fallback

        config_map = {
            Intent.QUESTION_EXAMPLE: self.config.strategies.question_example,
            Intent.QUESTION_HOWTO: self.config.strategies.question_howto,
            Intent.HELP_DEBUG: self.config.strategies.help_debug,
            Intent.HELP_REVIEW: self.config.strategies.help_review,
            Intent.CLARIFICATION: self.config.strategies.clarification,
        }
        return config_map.get(intent, self.config.strategies.fallback)

    async def _ensure_code_context(
        self,
        context: ConversationContext,
        classification: IntentClassification,
    ) -> None:
        """
        Ensure code context is available for code-related intents.

        Downloads submission artifact if:
        1. The intent requires code (HELP_DEBUG, HELP_REVIEW)
        2. No code is currently loaded in the context
        3. Or checks if the user's description mentions needing to look at code

        Args:
            context: The conversation context
            classification: The intent classification
        """
        from computor_agent.tutor.intents import Intent

        # Check if this intent typically needs code
        code_related_intents = {Intent.HELP_DEBUG, Intent.HELP_REVIEW}
        needs_code = (
            classification.intent in code_related_intents
            or self._user_intent_needs_code(classification.user_intent_description)
        )

        logger.debug(f"Intent: {classification.intent}, needs_code: {needs_code}, has_code: {context.has_code}")

        # If we already have code or don't need it, return
        if not needs_code:
            logger.debug("Intent does not require code, skipping download")
            return

        if context.has_code:
            logger.debug("Code already loaded, skipping download")
            return

        # Try to download the latest submission
        logger.info("Intent requires code but none loaded - attempting to download submission")

        # Get identifiers from context
        course_member_id = (
            context.student.course_member_ids[0]
            if context.student.course_member_ids
            else None
        )
        course_content_id = (
            context.assignment.course_content_id
            if context.assignment
            else None
        )

        # Try to download submission
        # Use submission_group_id if available, otherwise use course_content_id + course_member_id
        if context.submission_group_id:
            logger.debug(f"Using submission_group_id for download: {context.submission_group_id}")
            submission_code = await self.context_builder.download_submission_code(
                submission_group_id=context.submission_group_id,
                submit_only=False,  # Include test uploads too
            )
        elif course_content_id and course_member_id:
            logger.debug(f"Using course_content_id + course_member_id for download: {course_content_id} + {course_member_id}")
            submission_code = await self.context_builder.download_submission_code(
                course_content_id=course_content_id,
                course_member_id=course_member_id,
                submit_only=False,  # Include test uploads too
            )
        else:
            logger.warning("No valid parameters for submission download (need submission_group_id OR course_content_id+course_member_id)")
            submission_code = None

        if submission_code:
            context.student_code = submission_code
            logger.info(f"Successfully downloaded submission with {len(submission_code.files)} files")
            for filename in list(submission_code.files.keys())[:5]:
                logger.debug(f"  - {filename}")
        else:
            # Mark that we tried but found no submission
            context.no_submission_available = True
            logger.info("No submission found for student - will inform them to submit code")

    def _user_intent_needs_code(self, user_intent_description: str) -> bool:
        """
        Check if the user's intent description suggests they need code analysis.

        Args:
            user_intent_description: The LLM's description of what the user wants

        Returns:
            True if the description suggests code analysis is needed
        """
        # Keywords that suggest code analysis is needed
        code_keywords = [
            "debug", "error", "bug", "fix", "review", "code",
            "implementation", "solution", "function", "method",
            "line", "syntax", "compile", "runtime", "exception",
            "traceback", "stack", "segfault", "crash", "fails"
        ]

        description_lower = user_intent_description.lower()
        return any(keyword in description_lower for keyword in code_keywords)

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
