"""
Intent Classifier for the Tutor AI Agent.

Uses an LLM to classify student messages into intents,
which then determine which response strategy to use.

Design decisions:
- 100% LLM-based classification (no rules, no keywords)
- Always returns user_intent_description for logging/fallback
- Returns intent=None when no defined intent matches
"""

import json
import logging
from typing import TYPE_CHECKING, Optional, Protocol

from computor_agent.tutor.intents.types import (
    Intent,
    IntentClassification,
    MESSAGING_INTENTS,
)
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

    Each intent maps to a specific response strategy.
    When no intent matches, returns intent=None with user_intent_description,
    and the FallbackStrategy handles the response.

    Usage:
        classifier = IntentClassifier(llm=llm_client)
        classification = await classifier.classify(context)

        if classification.intent:
            strategy = registry.get_strategy(classification.intent)
        else:
            strategy = registry.fallback_strategy
    """

    def __init__(
        self,
        llm: LLMClient,
        confidence_threshold: float = 0.5,
        available_intents: Optional[list[Intent]] = None,
    ) -> None:
        """
        Initialize the intent classifier.

        Args:
            llm: LLM client for classification
            confidence_threshold: Minimum confidence to accept classification
            available_intents: List of intents to match against (defaults to MESSAGING_INTENTS)
        """
        self.llm = llm
        self.confidence_threshold = confidence_threshold
        self.available_intents = available_intents or MESSAGING_INTENTS

    def get_available_intents(self) -> list[Intent]:
        """Return the list of intents this classifier can match."""
        return self.available_intents

    def _build_intents_description(self) -> str:
        """Build the intents description for the prompt."""
        lines = []
        for intent in self.available_intents:
            lines.append(f"- {intent.value.upper()}: {intent.description}")
        return "\n".join(lines)

    async def classify(
        self,
        context: "ConversationContext",
    ) -> IntentClassification:
        """
        Classify the intent of the student's message.

        Args:
            context: The conversation context

        Returns:
            IntentClassification with intent (or None) and user_intent_description
        """
        # Handle submission trigger separately (for grading task)
        if context.trigger_submission is not None and context.trigger_message is None:
            return IntentClassification(
                intent=Intent.SUBMISSION_REVIEW,
                confidence=1.0,
                user_intent_description="Submit code for grading review",
                reasoning="Triggered by submission artifact with submit=True",
            )

        if not context.trigger_message:
            return IntentClassification(
                intent=None,
                confidence=0.0,
                user_intent_description="No message provided",
                reasoning="No message to classify",
            )

        # Build previous context for classification
        previous_context = context.get_formatted_previous_messages(max_messages=3)

        prompt = INTENT_CLASSIFICATION_PROMPT.format(
            student_message=context.trigger_message.content,
            previous_context=previous_context,
            available_intents=self._build_intents_description(),
        )

        try:
            response = await self.llm.complete(prompt, max_tokens=400)
            return self._parse_response(response)
        except Exception as e:
            logger.warning(f"Intent classification failed: {e}")
            return IntentClassification(
                intent=None,
                confidence=0.0,
                user_intent_description="Unable to determine user intent",
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
            available_intents=self._build_intents_description(),
        )

        try:
            response = await self.llm.complete(prompt, max_tokens=400)
            return self._parse_response(response)
        except Exception as e:
            logger.warning(f"Intent classification failed: {e}")
            return IntentClassification(
                intent=None,
                confidence=0.0,
                user_intent_description="Unable to determine user intent",
                reasoning=f"Classification failed: {e}",
            )

    def _parse_response(self, response: str) -> IntentClassification:
        """Parse the LLM response into an IntentClassification."""
        try:
            # Extract JSON from response
            json_str = self._extract_json(response)
            data = json.loads(json_str)

            # user_intent_description is REQUIRED
            user_intent_description = data.get(
                "user_intent_description",
                "Unable to determine user intent"
            )

            # intent may be null/None if no match
            intent = None
            confidence = 0.0

            intent_str = data.get("intent")
            if intent_str and intent_str.lower() != "null":
                intent = self._parse_intent(intent_str)
                confidence = float(data.get("confidence", 0.5))

                # Apply confidence threshold
                if confidence < self.confidence_threshold:
                    logger.debug(
                        f"Low confidence ({confidence:.2f}) for {intent.value}, "
                        f"setting intent to None"
                    )
                    intent = None
                    confidence = 0.0

            reasoning = data.get("reasoning")
            secondary_intent = None

            if data.get("secondary_intent"):
                secondary_str = data["secondary_intent"]
                if secondary_str and secondary_str.lower() != "null":
                    secondary_intent = self._parse_intent(secondary_str)

            return IntentClassification(
                intent=intent,
                confidence=confidence,
                user_intent_description=user_intent_description,
                reasoning=reasoning,
                secondary_intent=secondary_intent,
            )

        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            logger.warning(f"Failed to parse classification response: {e}")
            return IntentClassification(
                intent=None,
                confidence=0.0,
                user_intent_description="Unable to determine user intent",
                reasoning=f"Parse error: {e}",
            )

    def _extract_json(self, text: str) -> str:
        """Extract JSON object from text that may contain other content."""
        start = text.find("{")
        end = text.rfind("}") + 1

        if start == -1 or end == 0:
            raise ValueError("No JSON object found in response")

        return text[start:end]

    def _parse_intent(self, intent_str: str) -> Optional[Intent]:
        """Parse intent string to enum."""
        intent_map = {
            "QUESTION_EXAMPLE": Intent.QUESTION_EXAMPLE,
            "QUESTION_HOWTO": Intent.QUESTION_HOWTO,
            "HELP_DEBUG": Intent.HELP_DEBUG,
            "HELP_REVIEW": Intent.HELP_REVIEW,
            "SUBMISSION_REVIEW": Intent.SUBMISSION_REVIEW,
            "CLARIFICATION": Intent.CLARIFICATION,
            # Also support lowercase
            "question_example": Intent.QUESTION_EXAMPLE,
            "question_howto": Intent.QUESTION_HOWTO,
            "help_debug": Intent.HELP_DEBUG,
            "help_review": Intent.HELP_REVIEW,
            "submission_review": Intent.SUBMISSION_REVIEW,
            "clarification": Intent.CLARIFICATION,
        }
        return intent_map.get(intent_str)
