"""
Intent Classifier for the Tutor AI Agent.

Uses an LLM to classify student messages into intents,
which then determine which response strategy to use.
"""

import json
import logging
from typing import TYPE_CHECKING, Optional, Protocol

from computor_agent.tutor.intents.types import Intent, IntentClassification
from computor_agent.tutor.prompts.templates import INTENT_CLASSIFICATION_PROMPT

if TYPE_CHECKING:
    from computor_agent.tutor.context import ConversationContext

logger = logging.getLogger(__name__)


class LLMClient(Protocol):
    """Protocol for LLM client used by IntentClassifier."""

    async def complete(self, prompt: str, *, max_tokens: int = 500) -> str:
        """Generate a completion for the given prompt."""
        ...


class IntentClassifier:
    """
    Classifies student messages into intents.

    Each intent maps to a specific response strategy:
    - QUESTION_EXAMPLE -> Strategy for assignment questions
    - QUESTION_HOWTO -> Strategy for how-to questions
    - HELP_DEBUG -> Strategy for debugging help
    - HELP_REVIEW -> Strategy for code review
    - SUBMISSION_REVIEW -> Strategy for official submission review
    - CLARIFICATION -> Strategy for follow-up questions
    - OTHER -> Fallback strategy

    Usage:
        classifier = IntentClassifier(llm=llm_client)
        classification = await classifier.classify(context)
        strategy = registry.get_strategy(classification.intent)
    """

    def __init__(
        self,
        llm: LLMClient,
        default_intent: Intent = Intent.OTHER,
        confidence_threshold: float = 0.5,
    ) -> None:
        """
        Initialize the intent classifier.

        Args:
            llm: LLM client for classification
            default_intent: Intent to use if classification fails
            confidence_threshold: Minimum confidence to accept classification
        """
        self.llm = llm
        self.default_intent = default_intent
        self.confidence_threshold = confidence_threshold

    async def classify(
        self,
        context: "ConversationContext",
    ) -> IntentClassification:
        """
        Classify the intent of the student's message.

        Args:
            context: The conversation context

        Returns:
            IntentClassification with intent and confidence
        """
        # Handle submission trigger separately
        if context.trigger_submission is not None and context.trigger_message is None:
            # This is a submission-triggered context (no message)
            return IntentClassification(
                intent=Intent.SUBMISSION_REVIEW,
                confidence=1.0,
                reasoning="Triggered by submission artifact with submit=True",
            )

        if not context.trigger_message:
            return IntentClassification(
                intent=self.default_intent,
                confidence=0.0,
                reasoning="No message to classify",
            )

        # Build previous context for classification
        previous_context = context.get_formatted_previous_messages(max_messages=3)

        prompt = INTENT_CLASSIFICATION_PROMPT.format(
            student_message=context.trigger_message.content,
            previous_context=previous_context,
        )

        try:
            response = await self.llm.complete(prompt, max_tokens=300)
            return self._parse_response(response)
        except Exception as e:
            logger.warning(f"Intent classification failed: {e}")
            return IntentClassification(
                intent=self.default_intent,
                confidence=0.0,
                reasoning=f"Classification failed: {e}",
            )

    async def classify_message(
        self,
        message: str,
        previous_context: Optional[str] = None,
    ) -> IntentClassification:
        """
        Classify a single message without full context.

        Convenience method for testing or simple classification.

        Args:
            message: The message to classify
            previous_context: Optional previous conversation context

        Returns:
            IntentClassification
        """
        prompt = INTENT_CLASSIFICATION_PROMPT.format(
            student_message=message,
            previous_context=previous_context or "(No previous messages)",
        )

        try:
            response = await self.llm.complete(prompt, max_tokens=300)
            return self._parse_response(response)
        except Exception as e:
            logger.warning(f"Intent classification failed: {e}")
            return IntentClassification(
                intent=self.default_intent,
                confidence=0.0,
                reasoning=f"Classification failed: {e}",
            )

    def _parse_response(self, response: str) -> IntentClassification:
        """Parse the LLM response into an IntentClassification."""
        try:
            # Extract JSON from response
            json_str = self._extract_json(response)
            data = json.loads(json_str)

            intent = self._parse_intent(data.get("intent", "OTHER"))
            confidence = float(data.get("confidence", 0.5))
            reasoning = data.get("reasoning")
            secondary_intent = None

            if data.get("secondary_intent"):
                secondary_intent = self._parse_intent(data["secondary_intent"])

            # Apply confidence threshold
            if confidence < self.confidence_threshold:
                logger.debug(
                    f"Low confidence ({confidence:.2f}) for {intent.value}, "
                    f"using default {self.default_intent.value}"
                )
                return IntentClassification(
                    intent=self.default_intent,
                    confidence=confidence,
                    reasoning=f"Low confidence: {reasoning}",
                    secondary_intent=intent,
                )

            return IntentClassification(
                intent=intent,
                confidence=confidence,
                reasoning=reasoning,
                secondary_intent=secondary_intent,
            )

        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            logger.warning(f"Failed to parse classification response: {e}")
            return IntentClassification(
                intent=self.default_intent,
                confidence=0.0,
                reasoning=f"Parse error: {e}",
            )

    def _extract_json(self, text: str) -> str:
        """Extract JSON object from text that may contain other content."""
        start = text.find("{")
        end = text.rfind("}") + 1

        if start == -1 or end == 0:
            raise ValueError("No JSON object found in response")

        return text[start:end]

    def _parse_intent(self, intent_str: str) -> Intent:
        """Parse intent string to enum."""
        intent_map = {
            "QUESTION_EXAMPLE": Intent.QUESTION_EXAMPLE,
            "QUESTION_HOWTO": Intent.QUESTION_HOWTO,
            "HELP_DEBUG": Intent.HELP_DEBUG,
            "HELP_REVIEW": Intent.HELP_REVIEW,
            "SUBMISSION_REVIEW": Intent.SUBMISSION_REVIEW,
            "CLARIFICATION": Intent.CLARIFICATION,
            "OTHER": Intent.OTHER,
            # Also support lowercase
            "question_example": Intent.QUESTION_EXAMPLE,
            "question_howto": Intent.QUESTION_HOWTO,
            "help_debug": Intent.HELP_DEBUG,
            "help_review": Intent.HELP_REVIEW,
            "submission_review": Intent.SUBMISSION_REVIEW,
            "clarification": Intent.CLARIFICATION,
            "other": Intent.OTHER,
        }
        return intent_map.get(intent_str, Intent.OTHER)
