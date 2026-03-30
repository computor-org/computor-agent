"""
Tutor Agent orchestrator for the Computor Agent.

This is the main entry point for tutor functionality. It:
1. Builds context from API data
2. Runs security checks (optional)
3. Generates response via single LLM call
4. Sends the response

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
from computor_agent.tutor.prompts.templates import TUTOR_SYSTEM_PROMPT, PERSONALITY_PROMPTS
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

            # Run security check (optional)
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

            # Try to download submission code (always attempt — the LLM
            # can decide itself whether the student needs code help)
            await self._ensure_code_context(context)

            # Build unified system prompt with all available context
            system_prompt = self._build_system_prompt(context)
            user_message = context.trigger_message.content if context.trigger_message else "(No message)"

            # Single LLM call — no intent classification needed
            logger.info("Generating response via unified prompt")
            response_content = await self.llm.complete(
                prompt=user_message,
                system_prompt=system_prompt,
                max_tokens=self.config.strategies.fallback.max_response_tokens,
                temperature=self.config.strategies.fallback.temperature,
            )

            response = StrategyResponse(
                message_content=response_content,
                strategy_name="unified",
            )

            # Send response if configured
            message_sent = False
            response_message_id = None
            if send_response and response.message_content:
                # Add response tag to title for trigger detection
                formatted_title = self._format_response_title(response.message_title)

                # Reply to the triggering message to create a chain
                parent_id = reply_to_message_id or message.get("id")

                # When replying (parent_id set), don't set target — inherited from parent
                message_data: dict[str, Any] = {
                    "content": response.message_content,
                    "title": formatted_title,
                }
                if parent_id:
                    message_data["parent_id"] = parent_id
                else:
                    message_data["submission_group_id"] = submission_group_id

                logger.info(f"Creating message with data: {message_data}")
                created_message = await self.client.messages.create(data=message_data)
                message_sent = True
                response_message_id = created_message.id
            elif send_response:
                logger.warning(
                    f"LLM returned empty response for message {message.get('id')} "
                    f"in submission group {submission_group_id} — not sending a reply"
                )

            # Only mark the original message as read if a response was sent
            # (or if sending was disabled). If the LLM returned empty content,
            # leave the message unread so it can be retried on next catch-up.
            message_id = message.get("id")
            if message_id and (message_sent or not send_response):
                try:
                    await self.client.messages.reads(id=message_id)
                except Exception as e:
                    logger.warning(f"Failed to mark message {message_id} as read: {e}")

            elapsed_ms = (time.perf_counter() - start_time) * 1000

            # If we were supposed to send a response but couldn't (empty LLM output),
            # report as failure so the scheduler doesn't mark the message as read.
            success = message_sent or not send_response
            return ProcessingResult(
                success=success,
                error="LLM returned empty response" if (send_response and not message_sent) else None,
                message_sent=message_sent,
                response=response,
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
        response_tag = f"#{self.config.triggers.response_tag_string}"  # e.g., "#ai-response"
        base_title = title or default
        if base_title:
            return f"{response_tag} {base_title}"
        return response_tag

    def _build_system_prompt(self, context: ConversationContext) -> str:
        """Build the unified system prompt with all available context."""
        # Personality
        tone = self.config.personality.tone.value
        try:
            from computor_agent.tutor.prompts.loader import get_personality_prompt
            personality = get_personality_prompt(tone)
        except Exception:
            personality = PERSONALITY_PROMPTS.get(tone, PERSONALITY_PROMPTS["friendly_professional"])
        personality = personality.format(tutor_name=self.config.personality.name)

        # Try custom "tutor" prompt from loader, fall back to built-in
        try:
            from computor_agent.tutor.prompts.loader import get_prompt_loader
            loader = get_prompt_loader()
            # Only use loader if there's an explicit tutor.md — don't fall back to old prompts
            template = loader._strategy_prompts.get("tutor")
        except Exception:
            template = None
        if not template:
            template = TUTOR_SYSTEM_PROMPT

        # Assignment
        assignment_section = ""
        if context.assignment:
            parts = []
            if context.assignment.title:
                parts.append(f"Title: {context.assignment.title}")
            if context.assignment.description:
                parts.append(context.assignment.description)
            if parts:
                assignment_section = f"Assignment:\n---\n{chr(10).join(parts)}\n---"

        # Student code
        code_section = ""
        if context.has_code:
            code_section = f"Student's Code:\n---\n{context.get_formatted_code()}\n---"
        elif context.no_submission_available:
            code_section = "(No code available — student has not submitted any code yet)"

        # Test results
        test_results_section = ""
        if context.has_test_results:
            test_results_section = f"Test Results:\n---\n{context.test_results.format_for_prompt()}\n---"

        # Previous messages
        previous_messages_section = ""
        prev = context.get_formatted_previous_messages()
        if prev and prev.strip():
            previous_messages_section = f"Previous Conversation:\n---\n{prev}\n---"

        # Reference comparison
        reference_comparison_section = ""
        if context.has_reference_comparison:
            reference_comparison_section = f"Reference Comparison:\n---\n{context.reference_comparison.format_for_prompt(max_diffs=3, max_lines_per_diff=30)}\n---"

        return template.format(
            personality_prompt=personality,
            language=self.config.personality.language,
            assignment_section=assignment_section,
            code_section=code_section,
            test_results_section=test_results_section,
            previous_messages_section=previous_messages_section,
            reference_comparison_section=reference_comparison_section,
        )

    async def _ensure_code_context(self, context: ConversationContext) -> None:
        """Try to download submission code if not already available."""
        if context.has_code:
            return

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

        if context.submission_group_id:
            submission_code = await self.context_builder.download_submission_code(
                submission_group_id=context.submission_group_id,
                submit_only=False,
            )
        elif course_content_id and course_member_id:
            submission_code = await self.context_builder.download_submission_code(
                course_content_id=course_content_id,
                course_member_id=course_member_id,
                submit_only=False,
            )
        else:
            submission_code = None

        if submission_code:
            context.student_code = submission_code
            logger.info(f"Downloaded submission with {len(submission_code.files)} files")
        else:
            context.no_submission_available = True
            logger.info("No submission found for student")

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
