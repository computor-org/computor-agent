"""
Tests for the Tutor AI Agent module.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from pathlib import Path

from computor_agent.tutor import (
    TutorConfig,
    PersonalityConfig,
    SecurityConfig,
    ContextConfig,
    GradingConfig,
    Intent,
    IntentClassification,
    TriggerType,
    ConversationContext,
    ThreatType,
    ThreatLevel,
)
from computor_agent.tutor.context import (
    MessageInfo,
    SubmissionInfo,
    StudentInfo,
    AssignmentInfo,
    CodeContext,
)
from computor_agent.tutor.security.types import ThreatDetection, SecurityCheckResult
from computor_agent.tutor.intents.types import IntentClassification


class TestTutorConfig:
    """Tests for TutorConfig."""

    def test_default_config(self):
        """Test creating config with defaults."""
        config = TutorConfig()

        assert config.personality.name == "Tutor AI"
        assert config.security.enabled is True
        assert config.security.require_confirmation is True
        assert config.context.include_previous_messages == 3
        assert config.grading.enabled is False

    def test_config_from_dict(self):
        """Test creating config from dict."""
        data = {
            "personality": {
                "name": "Custom Tutor",
                "tone": "strict",
                "language": "de",
            },
            "security": {
                "enabled": False,
            },
            "context": {
                "include_previous_messages": 5,
                "student_notes_enabled": True,
            },
            "grading": {
                "enabled": True,
                "auto_submit_grade": True,
            },
        }

        config = TutorConfig.from_dict(data)

        assert config.personality.name == "Custom Tutor"
        assert config.personality.tone.value == "strict"
        assert config.personality.language == "de"
        assert config.security.enabled is False
        assert config.context.include_previous_messages == 5
        assert config.context.student_notes_enabled is True
        assert config.grading.enabled is True
        assert config.grading.auto_submit_grade is True

    def test_config_to_dict(self):
        """Test exporting config to dict."""
        config = TutorConfig()
        data = config.to_dict()

        assert "personality" in data
        assert "security" in data
        assert "context" in data
        assert "grading" in data
        assert "strategies" in data


class TestIntent:
    """Tests for Intent enum."""

    def test_intent_values(self):
        """Test all intent values exist."""
        assert Intent.QUESTION_EXAMPLE.value == "question_example"
        assert Intent.QUESTION_HOWTO.value == "question_howto"
        assert Intent.HELP_DEBUG.value == "help_debug"
        assert Intent.HELP_REVIEW.value == "help_review"
        assert Intent.SUBMISSION_REVIEW.value == "submission_review"
        assert Intent.CLARIFICATION.value == "clarification"
        assert Intent.OTHER.value == "other"


class TestIntentClassification:
    """Tests for IntentClassification."""

    def test_basic_classification(self):
        """Test creating a classification."""
        classification = IntentClassification(
            intent=Intent.HELP_DEBUG,
            confidence=0.85,
            reasoning="Student mentioned error message",
        )

        assert classification.intent == Intent.HELP_DEBUG
        assert classification.confidence == 0.85
        assert "error" in classification.reasoning

    def test_classification_with_secondary(self):
        """Test classification with secondary intent."""
        classification = IntentClassification(
            intent=Intent.QUESTION_EXAMPLE,
            confidence=0.6,
            secondary_intent=Intent.QUESTION_HOWTO,
        )

        assert classification.intent == Intent.QUESTION_EXAMPLE
        assert classification.secondary_intent == Intent.QUESTION_HOWTO


class TestConversationContext:
    """Tests for ConversationContext."""

    def test_basic_context(self):
        """Test creating basic context."""
        context = ConversationContext(
            trigger_type=TriggerType.MESSAGE,
            submission_group_id="sg-123",
        )

        assert context.trigger_type == TriggerType.MESSAGE
        assert context.submission_group_id == "sg-123"
        assert context.trigger_message is None
        assert context.has_code is False
        assert context.has_reference is False

    def test_context_with_message(self):
        """Test context with trigger message."""
        msg = MessageInfo(
            id="msg-1",
            title="Help needed",
            content="I can't find the bug!",
            author_id="user-1",
            is_from_student=True,
        )

        context = ConversationContext(
            trigger_type=TriggerType.MESSAGE,
            submission_group_id="sg-123",
            trigger_message=msg,
        )

        assert context.student_message == "I can't find the bug!"
        assert context.trigger_message.id == "msg-1"

    def test_context_with_code(self):
        """Test context with student code."""
        code = CodeContext(
            files={
                "main.py": "print('hello')",
                "utils.py": "def helper(): pass",
            },
            total_lines=2,
        )

        context = ConversationContext(
            trigger_type=TriggerType.MESSAGE,
            submission_group_id="sg-123",
            student_code=code,
        )

        assert context.has_code is True
        formatted = context.get_formatted_code()
        assert "main.py" in formatted
        assert "print('hello')" in formatted

    def test_primary_user_id(self):
        """Test getting primary user ID."""
        student = StudentInfo(
            user_ids=["user-1", "user-2"],
            names=["Alice", "Bob"],
        )

        context = ConversationContext(
            trigger_type=TriggerType.MESSAGE,
            submission_group_id="sg-123",
            student=student,
        )

        assert context.primary_user_id == "user-1"

    def test_get_formatted_previous_messages(self):
        """Test formatting previous messages."""
        messages = [
            MessageInfo(id="1", title="", content="Hello", author_id="s1", is_from_student=True),
            MessageInfo(id="2", title="", content="Hi there!", author_id="t1", is_from_student=False),
            MessageInfo(id="3", title="", content="Need help", author_id="s1", is_from_student=True),
        ]

        context = ConversationContext(
            trigger_type=TriggerType.MESSAGE,
            submission_group_id="sg-123",
            previous_messages=messages,
        )

        formatted = context.get_formatted_previous_messages(max_messages=2)
        assert "[Student]: Hi there!" not in formatted  # First message skipped
        assert "[Tutor]: Hi there!" in formatted
        assert "[Student]: Need help" in formatted

    def test_destroy(self):
        """Test context cleanup."""
        messages = [MessageInfo(id="1", title="", content="test", author_id="s1")]
        code = CodeContext(files={"main.py": "code"})

        context = ConversationContext(
            trigger_type=TriggerType.MESSAGE,
            submission_group_id="sg-123",
            previous_messages=messages,
            student_code=code,
            student_notes="Some notes",
        )

        context.destroy()

        assert len(context.previous_messages) == 0
        assert len(context.student_code.files) == 0
        assert context.student_notes is None


class TestThreatDetection:
    """Tests for ThreatDetection."""

    def test_basic_detection(self):
        """Test creating a threat detection."""
        detection = ThreatDetection(
            threat_type=ThreatType.PROMPT_INJECTION,
            level=ThreatLevel.HIGH,
            description="Attempted prompt injection",
            evidence="Ignore previous instructions...",
            source="message",
        )

        assert detection.threat_type == ThreatType.PROMPT_INJECTION
        assert detection.level == ThreatLevel.HIGH
        assert detection.source == "message"


class TestSecurityCheckResult:
    """Tests for SecurityCheckResult."""

    def test_safe_result(self):
        """Test creating a safe result."""
        result = SecurityCheckResult(is_safe=True)

        assert result.is_safe is True
        assert len(result.threats) == 0
        assert result.highest_threat_level == ThreatLevel.NONE
        assert result.should_block is False

    def test_unsafe_result(self):
        """Test result with threats."""
        threats = [
            ThreatDetection(
                threat_type=ThreatType.PROMPT_INJECTION,
                level=ThreatLevel.HIGH,
                description="Test",
            ),
            ThreatDetection(
                threat_type=ThreatType.HARASSMENT,
                level=ThreatLevel.MEDIUM,
                description="Test",
            ),
        ]

        result = SecurityCheckResult(
            is_safe=False,
            threats=threats,
            was_confirmed=True,
            confirmation_agreed=True,
        )

        assert result.is_safe is False
        assert len(result.threats) == 2
        assert result.highest_threat_level == ThreatLevel.HIGH
        assert result.should_block is True
        assert result.was_confirmed is True

    def test_to_log_dict(self):
        """Test converting result to log dict."""
        result = SecurityCheckResult(
            is_safe=False,
            threats=[
                ThreatDetection(
                    threat_type=ThreatType.MALICIOUS_CODE,
                    level=ThreatLevel.CRITICAL,
                    description="Found backdoor",
                ),
            ],
            submission_group_id="sg-123",
            user_id="user-1",
        )

        log_dict = result.to_log_dict()

        assert log_dict["is_safe"] is False
        assert log_dict["threat_count"] == 1
        assert log_dict["highest_level"] == "critical"
        assert log_dict["submission_group_id"] == "sg-123"


class TestThreatLevels:
    """Tests for threat level ordering."""

    def test_should_block_high(self):
        """Test that HIGH level blocks."""
        result = SecurityCheckResult(
            is_safe=False,
            threats=[
                ThreatDetection(
                    threat_type=ThreatType.PROMPT_INJECTION,
                    level=ThreatLevel.HIGH,
                    description="Test",
                )
            ],
        )
        assert result.should_block is True

    def test_should_block_critical(self):
        """Test that CRITICAL level blocks."""
        result = SecurityCheckResult(
            is_safe=False,
            threats=[
                ThreatDetection(
                    threat_type=ThreatType.MALICIOUS_CODE,
                    level=ThreatLevel.CRITICAL,
                    description="Test",
                )
            ],
        )
        assert result.should_block is True

    def test_should_not_block_medium(self):
        """Test that MEDIUM level doesn't block."""
        result = SecurityCheckResult(
            is_safe=False,
            threats=[
                ThreatDetection(
                    threat_type=ThreatType.HARASSMENT,
                    level=ThreatLevel.MEDIUM,
                    description="Test",
                )
            ],
        )
        assert result.should_block is False

    def test_should_not_block_low(self):
        """Test that LOW level doesn't block."""
        result = SecurityCheckResult(
            is_safe=False,
            threats=[
                ThreatDetection(
                    threat_type=ThreatType.OTHER,
                    level=ThreatLevel.LOW,
                    description="Test",
                )
            ],
        )
        assert result.should_block is False
