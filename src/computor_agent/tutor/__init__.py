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
    │                  TRIGGER CHECKER                         │
    │  Checks for:                                             │
    │  - Messages with request tags (e.g., #ai::request)      │
    │  - Replies in conversation chains where AI responded    │
    │  - Submission artifacts with submit=True                │
    └─────────────────────────────────────────────────────────┘
                               │
                               ▼
    ┌─────────────────────────────────────────────────────────┐
    │              CONVERSATION CONTEXT                        │
    │  Fresh per interaction, contains:                        │
    │  - Trigger (message or submission)                       │
    │  - Message chain (via parent_id links)                  │
    │  - AI's previous notes about this context               │
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
    │  - Post reply to message chain (with parent_id)         │
    │  - Tag response with #ai::response                      │
    │  - Optionally post grade                                │
    │  - Save AI notes for future context                     │
    └─────────────────────────────────────────────────────────┘

Conversation Model:
    - Conversations are message chains linked by parent_id
    - A conversation starts when a message has a request tag
    - The AI responds as a reply (with parent_id)
    - Any student reply in the chain triggers another AI response
    - No external state tracking needed - the chain IS the conversation

Example:
    ```python
    from computor_agent.tutor import TutorAgent
    from computor_agent.settings import ComputorConfig
    from computor_client import ComputorClient

    # Load unified configuration (includes backend, llm, credentials, tutor)
    config = ComputorConfig.from_file("~/.computor/config.yaml")
    tutor_config = config.get_tutor_config()
    git_credentials = config.get_credentials_store()

    async with ComputorClient(base_url=config.backend.url) as client:
        # Authenticate (API token or basic auth)
        if config.backend.auth_method == "api_token":
            client.headers["X-API-Token"] = config.backend.get_api_token()
        else:
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

        # Handle a submission (typically called by scheduler)
        await agent.process_submission(
            submission_group_id="sg-123",
            artifact_id="art-456",
            course_member_id="cm-789",
            course_content_id="cc-101",
            submit_grade=True,  # Will auto-grade if tutor.grading.enabled
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
    NotesConfig,
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
from computor_agent.tutor.summary_store import SummaryStore, AgentNote

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
    "NotesConfig",
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
    # Summary storage (AI's notes to itself)
    "SummaryStore",
    "AgentNote",
]
