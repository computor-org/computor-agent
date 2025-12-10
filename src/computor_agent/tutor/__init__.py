"""
Tutor AI Agent for the Computor platform.

This module provides an AI-powered tutor agent that can:
- Respond to student messages about assignments
- Review code submissions
- Provide feedback and optionally grades
- Detect and block malicious inputs

Architecture:
    ┌─────────────────────────────────────────────────────────┐
    │                      SCHEDULER                           │
    │  Polls for: new messages, new submissions (submit=true) │
    └─────────────────────────────────────────────────────────┘
                               │
                               ▼
    ┌─────────────────────────────────────────────────────────┐
    │              CONVERSATION CONTEXT                        │
    │  Fresh per interaction, contains:                        │
    │  - Trigger (message or submission)                       │
    │  - Previous messages (configurable N)                    │
    │  - Course member comments (optional)                     │
    │  - Student notes from filesystem (optional)              │
    │  - Assignment description                                │
    │  - Student repository code                               │
    └─────────────────────────────────────────────────────────┘
                               │
                               ▼
    ┌─────────────────────────────────────────────────────────┐
    │                   SECURITY GATE                          │
    │  1. Detect threats in message + code (LLM)              │
    │  2. If suspicious → Confirm with 2nd LLM                │
    │  3. If confirmed → Log & block                          │
    └─────────────────────────────────────────────────────────┘
                               │
                               ▼ (if safe)
    ┌─────────────────────────────────────────────────────────┐
    │                 INTENT CLASSIFIER                        │
    │  Determines what student wants:                          │
    │  - QUESTION_EXAMPLE, QUESTION_HOWTO                     │
    │  - HELP_DEBUG, HELP_REVIEW                              │
    │  - SUBMISSION_REVIEW (auto for submissions)             │
    └─────────────────────────────────────────────────────────┘
                               │
                               ▼
    ┌─────────────────────────────────────────────────────────┐
    │                 STRATEGY EXECUTOR                        │
    │  Each intent → Strategy with:                            │
    │  - System prompt (personality + context)                │
    │  - LLM call                                             │
    │  - Response formatting                                   │
    └─────────────────────────────────────────────────────────┘
                               │
                               ▼
    ┌─────────────────────────────────────────────────────────┐
    │                 RESPONSE HANDLER                         │
    │  - Post to /messages API                                │
    │  - Optionally post grade                                │
    │  - Log interaction                                       │
    │  - Update student notes file                            │
    └─────────────────────────────────────────────────────────┘

Example:
    ```python
    from computor_agent.tutor import TutorAgent, TutorConfig
    from computor_agent.settings import ComputorConfig
    from computor_client import ComputorClient

    # Load configuration
    config = ComputorConfig.from_file("~/.computor/config.yaml")
    tutor_config = TutorConfig.from_file("~/.computor/tutor.yaml")

    async with ComputorClient(base_url=config.backend.url) as client:
        await client.login(
            username=config.backend.username,
            password=config.backend.get_password(),
        )

        # Create tutor agent
        agent = TutorAgent(
            client=client,
            config=tutor_config,
            llm_provider=llm,
        )

        # Handle a message (typically called by scheduler)
        await agent.handle_message(
            submission_group_id="sg-123",
            message_id="msg-456",
        )
    ```
"""

from computor_agent.tutor.config import (
    TutorConfig,
    PersonalityConfig,
    SecurityConfig,
    ContextConfig,
    GradingConfig,
    StrategyConfig,
    TriggerConfig,
    TriggerTag,
)
from computor_agent.tutor.intents import Intent, IntentClassification, IntentClassifier
from computor_agent.tutor.security import (
    SecurityGate,
    SecurityCheckResult,
    ThreatType,
    ThreatLevel,
)
from computor_agent.tutor.strategies import StrategyRegistry, StrategyResponse
from computor_agent.tutor.context import ConversationContext, TriggerType
from computor_agent.tutor.context_builder import ContextBuilder
from computor_agent.tutor.agent import TutorAgent, ProcessingResult
from computor_agent.tutor.trigger import (
    TriggerChecker,
    TriggerCheckResult,
    MessageTrigger,
    SubmissionTrigger,
    should_tutor_respond,
    STAFF_ROLES,
)
from computor_agent.tutor.scheduler import TutorScheduler, SchedulerConfig
from computor_agent.tutor.client_adapter import TutorClientAdapter, TutorLLMAdapter

__all__ = [
    # Main agent
    "TutorAgent",
    "ProcessingResult",
    # Scheduler
    "TutorScheduler",
    "SchedulerConfig",
    # Adapters
    "TutorClientAdapter",
    "TutorLLMAdapter",
    # Trigger detection
    "TriggerChecker",
    "TriggerCheckResult",
    "MessageTrigger",
    "SubmissionTrigger",
    "should_tutor_respond",
    "STAFF_ROLES",
    # Configuration
    "TutorConfig",
    "PersonalityConfig",
    "SecurityConfig",
    "ContextConfig",
    "GradingConfig",
    "StrategyConfig",
    "TriggerConfig",
    "TriggerTag",
    # Context
    "ConversationContext",
    "ContextBuilder",
    "TriggerType",
    # Intent
    "Intent",
    "IntentClassification",
    "IntentClassifier",
    # Security
    "SecurityGate",
    "SecurityCheckResult",
    "ThreatType",
    "ThreatLevel",
    # Strategies
    "StrategyRegistry",
    "StrategyResponse",
]
