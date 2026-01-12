# Tutor Agent: Messaging (Help Conversations)

This document describes the **messaging task** of the Tutor AI Agent - helping students through conversations.

> **Note**: This is separate from the **grading task** (submission review), which is documented in [tutor-grading.md](./tutor-grading.md) and will be implemented later.

---

## Overview

The messaging agent responds to student questions and help requests in a conversation format.

| Aspect | Description |
|--------|-------------|
| **Purpose** | Help students with questions, debugging, code review |
| **Trigger** | Message with `#ai::request` tag OR reply in existing AI conversation |
| **Output** | Response message only (no grading) |
| **Context** | Conversation history, student code, assignment description |

---

## Conversation Model

Conversations are **message chains** linked by `parent_id`:

```
Student: "How do I fix this error?" #ai::request     ← ROOT (has request tag)
    │
    └── AI: "Try checking the array bounds..." #ai::response
            │
            └── Student: "I tried that but now I get..."  ← FOLLOW-UP (no tag needed)
                    │
                    └── AI: "Ah, in that case..."  #ai::response
```

**Key points:**
- A conversation **starts** when a message has a request tag
- The AI **responds** as a reply (with `parent_id` pointing to student's message)
- Any student **reply in the chain** triggers another AI response (no new tag needed)
- No external state tracking - the chain IS the conversation

---

## API Endpoints

### Detection (Polling)

| Endpoint | Purpose |
|----------|---------|
| `GET /tutors/course-members` | List members, filter by `unread_message_count > 0` |
| `GET /messages?submission_group_id=...&tags=ai::request&unread=true` | Find new conversations |
| `GET /messages?submission_group_id=...&unread=true` | Find follow-up replies |

### Context Gathering

| Endpoint | Purpose |
|----------|---------|
| `GET /tutors/course-members/{cm_id}/course-contents/{cc_id}` | Get course content details (for `directory` field) |
| `GET /students/courses/{course_id}` | Get course info (for repo paths) |
| GitLab API | Fetch assignment description (README) |

### Response

| Endpoint | Purpose |
|----------|---------|
| `POST /messages` | Send response (with `parent_id` for reply chain) |
| `POST /messages/{id}/reads` | Mark original message as read |

---

## Trigger Detection

### Scenario 1: New Conversation

A student starts a new conversation by adding a request tag to their message.

**Detection:**
```python
# Query for messages with request tags
messages = await client.messages.list(
    submission_group_id=sg_id,
    tags=["ai::request"],  # Configured request tags
    unread=True,
)

# If found → New conversation, student is the author
if messages:
    trigger = messages[0]  # Oldest unread with tag
    root_message_id = trigger.id
```

### Scenario 2: Follow-up Reply

A student replies to an existing AI conversation (no tag needed).

**Detection:**
```python
# Get all unread messages
unread = await client.messages.list(
    submission_group_id=sg_id,
    unread=True,
)

for message in unread:
    if message.parent_id:
        # Trace up the chain to find if AI participated
        root_id = await trace_conversation_root(message.parent_id)
        if root_id:
            # This is a follow-up in an AI conversation
            trigger = message
            break
```

**Tracing the chain:**
```python
async def trace_conversation_root(message_id: str) -> Optional[str]:
    """Find root of conversation if AI participated."""
    current_id = message_id
    found_ai_response = False
    root_id = None

    while current_id:
        message = await client.messages.get(id=current_id)

        # Check if AI responded in this chain
        if "#ai::response" in (message.title or ""):
            found_ai_response = True

        # Check if this is the root (has request tag)
        if "#ai::request" in (message.title or ""):
            root_id = current_id

        if not message.parent_id:
            # Reached root
            if root_id is None:
                root_id = current_id
            break

        current_id = message.parent_id

    # Only return if AI participated
    return root_id if found_ai_response else None
```

---

## Processing Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    MESSAGING FLOW                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. DETECT TRIGGER                                              │
│     ├─ Poll: GET /tutors/course-members                        │
│     │   → Filter: unread_message_count > 0                     │
│     ├─ For each member with messages:                          │
│     │   GET /messages?submission_group_id=...&unread=true      │
│     │   → Check for request tags (new conversation)            │
│     │   → Check for follow-up replies (existing conversation)  │
│     └─ Pick oldest unprocessed trigger                         │
│                                                                 │
│  2. GATHER CONTEXT                                              │
│     ├─ Fetch conversation history (trace parent chain)         │
│     ├─ Fetch student info (name, role)                         │
│     ├─ Fetch assignment description (from GitLab)              │
│     │   → course content.directory → README_en.md              │
│     ├─ Optionally: fetch student code (if helpful)             │
│     └─ Load AI notes for this student (memory)                 │
│                                                                 │
│  3. SECURITY CHECK (optional)                                   │
│     ├─ Scan message for prompt injection                       │
│     └─ If threat → block or log                                │
│                                                                 │
│  4. CLASSIFY INTENT                                             │
│     ├─ QUESTION_EXAMPLE - about assignment requirements        │
│     ├─ QUESTION_HOWTO - general programming question           │
│     ├─ HELP_DEBUG - needs debugging assistance                 │
│     ├─ HELP_REVIEW - wants code review                         │
│     ├─ CLARIFICATION - follow-up question                      │
│     └─ None + user_intent_description - unmatched intent       │
│                                                                 │
│  5. GENERATE RESPONSE                                           │
│     ├─ Select strategy based on intent (or FallbackStrategy)  │
│     ├─ Build prompt with context + user_intent_description    │
│     └─ Generate LLM response                                   │
│                                                                 │
│  6. SEND RESPONSE                                               │
│     ├─ POST /messages with parent_id (reply chain)             │
│     ├─ Add #ai::response tag to title                          │
│     └─ Mark original message as read                           │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Intent Classification

The agent classifies what the student wants to determine the response strategy.

| Intent | Description | Example Student Message |
|--------|-------------|-------------------------|
| `QUESTION_EXAMPLE` | About assignment requirements | "What does the function need to return?" |
| `QUESTION_HOWTO` | General programming how-to | "How do I read a file in Python?" |
| `HELP_DEBUG` | Has error, needs debugging | "I get IndexError on line 15" |
| `HELP_REVIEW` | Wants code review/feedback | "Can you check if my solution is correct?" |
| `CLARIFICATION` | Follow-up to previous answer | "What do you mean by 'boundary check'?" |

**Classification approach:**
- **100% LLM-based** - no rule-based detection, no keyword matching
- LLM always returns both:
  1. `user_intent_description` - natural language description of what the user wants
  2. `intent` - matched intent enum value (or `None` if no defined intent matches)
- Confidence score for the matched intent
- When no defined intent matches → `intent = None`, strategy uses `user_intent_description`

### Handling Unmatched Intents

When the student's request doesn't match any defined intent:

```python
@dataclass
class IntentClassification:
    intent: Intent | None              # None when no defined intent matches
    confidence: float
    reasoning: str | None = None
    user_intent_description: str       # ALWAYS populated by LLM
    secondary_intent: Intent | None = None
```

**The LLM prompt instructs:**
1. **Always** describe what the user wants (`user_intent_description`)
2. **Try** to match to a defined intent (if no match → `null`)
3. Provide confidence and reasoning

**Benefits:**
- `user_intent_description` is useful for logging and analytics
- `FallbackStrategy` can generate a helpful response using the description
- Clear signal when intent doesn't match (`intent = None`)

---

## Response Strategies

Each intent maps to a response strategy with specific behavior:

| Strategy | Focus | Includes |
|----------|-------|----------|
| `question_example` | Explain assignment | Assignment description, requirements |
| `question_howto` | Teach concept | General explanation, examples |
| `help_debug` | Find the bug | Error analysis, code inspection |
| `help_review` | Review code | Feedback, suggestions, style |
| `clarification` | Clarify previous answer | Previous conversation context |
| `fallback` | Handle unmatched intents | Uses `user_intent_description` to generate helpful response |

### Strategy Registry

```python
class StrategyRegistry:
    """Maps intents to strategies, with fallback for unmatched."""

    def __init__(
        self,
        strategies: dict[Intent, ResponseStrategy],
        fallback_strategy: ResponseStrategy,
    ):
        self.strategies = strategies
        self.fallback_strategy = fallback_strategy

    def get_strategy(self, classification: IntentClassification) -> ResponseStrategy:
        """Get the appropriate strategy for a classification."""
        if classification.intent is None:
            # No defined intent matched - use fallback
            return self.fallback_strategy

        return self.strategies.get(classification.intent, self.fallback_strategy)
```

The `FallbackStrategy` receives the full `IntentClassification` including `user_intent_description`, allowing it to generate a relevant response even when the intent isn't predefined.

---

## Context Data

### What the agent knows about the conversation:

```python
@dataclass
class MessageContext:
    # Trigger
    trigger_message: Message       # The message that triggered this
    is_follow_up: bool             # True if reply in existing conversation
    root_message_id: str           # Root of the conversation chain

    # Conversation
    previous_messages: list[Message]  # Up to N previous messages in chain

    # Student
    student_name: str
    student_role: str              # "_student", "_tutor", etc.

    # Assignment (optional)
    assignment_title: str
    assignment_description: str    # From README_en.md

    # Code (optional)
    student_code: dict[str, str]   # filename -> content

    # Memory
    ai_notes: str                  # Agent's notes about this student
```

---

## Configuration

```yaml
tutor:
  # Personality
  personality:
    name: "Tutor AI"
    tone: "friendly_professional"  # friendly_professional, strict, casual
    language: "en"

  # Security (optional)
  security:
    enabled: true
    check_messages: true
    block_on_threat: true

  # Context
  context:
    include_previous_messages: 3   # How many previous messages to include
    max_code_lines: 500            # Limit code context size

  # Triggers
  triggers:
    request_tags:
      - scope: "ai"
        value: "request"
    response_tag:
      scope: "ai"
      value: "response"

  # Strategy settings
  strategies:
    question_example:
      enabled: true
      max_response_tokens: 1000
      temperature: 0.7

    question_howto:
      enabled: true
      max_response_tokens: 1000
      temperature: 0.7

    help_debug:
      enabled: true
      max_response_tokens: 1500
      temperature: 0.5

    help_review:
      enabled: true
      max_response_tokens: 1500
      temperature: 0.5

    clarification:
      enabled: true
      max_response_tokens: 800
      temperature: 0.7

    other:
      enabled: true
      max_response_tokens: 500
      temperature: 0.7
```

---

## Code Structure (Messaging-Only)

### Files to Keep

| File | Purpose |
|------|---------|
| `trigger.py` | Message trigger detection (`check_message_trigger`) |
| `context.py` | `ConversationContext` for messaging |
| `context_builder.py` | `build_for_message()` method |
| `intents/` | Intent types and LLM classifier |
| `strategies/` | Response strategies (except `SubmissionReviewStrategy`) |
| `security/` | Prompt injection detection |
| `agent.py` | `process_message()` method only |
| `scheduler.py` | Polling loop (message-focused) |
| `config.py` | Configuration (messaging parts) |

### Files to Remove/Disable for Messaging

| File/Component | Reason |
|----------------|--------|
| `agent.py:process_submission()` | Grading task |
| `strategies/implementations.py:SubmissionReviewStrategy` | Grading task |
| `intents/types.py:SUBMISSION_REVIEW` | Grading task |
| `services/test_results.py` | Grading context |
| `services/reference.py` | Grading context |
| `services/history.py` | Grading context |
| `services/progress.py` | Grading context |
| `config.py:GradingConfig` | Grading task |

### Simplified Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        SCHEDULER                                 │
│  Polls: GET /tutors/course-members (unread_message_count > 0)  │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                    TRIGGER CHECKER                               │
│  - New conversation: message with #ai::request tag              │
│  - Follow-up: reply in AI conversation chain                   │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                   CONTEXT BUILDER                                │
│  - Conversation history                                         │
│  - Student info                                                 │
│  - Assignment description (from GitLab)                         │
│  - Student code (optional)                                      │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                   SECURITY GATE (optional)                       │
│  - Detect prompt injection                                      │
│  - Block or log threats                                         │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                  INTENT CLASSIFIER                               │
│  QUESTION_EXAMPLE | QUESTION_HOWTO | HELP_DEBUG                 │
│  HELP_REVIEW | CLARIFICATION | None (unmatched)                 │
│  Always returns: user_intent_description                        │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                  STRATEGY EXECUTOR                               │
│  - Select strategy based on intent                              │
│  - Build prompt with context                                    │
│  - Generate LLM response                                        │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                  RESPONSE HANDLER                                │
│  - POST /messages with parent_id                                │
│  - Add #ai::response tag                                        │
│  - Mark original as read                                        │
└─────────────────────────────────────────────────────────────────┘
```

---

## Object-Oriented Design

The tutor agent uses a clean separation between **general/reusable components** and **tutor-specific components**.

### Design Principles

1. **General components** can be reused by other agents (security, intent classification)
2. **Interfaces are abstract**, implementations are specific
3. **LLM is injected** via protocol/interface, not hardcoded
4. **Configuration is typed** and validated

### Component Hierarchy

```
┌─────────────────────────────────────────────────────────────────┐
│                    GENERAL COMPONENTS                           │
│  (Reusable by any agent)                                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  LLMClient (Protocol/Interface)                          │   │
│  │  - complete(prompt, system_prompt, max_tokens, temp)    │   │
│  │  - Implemented by: OpenAI, Ollama, etc.                 │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  SecurityGate (Abstract Base)                            │   │
│  │  - check(content, source) -> SecurityCheckResult        │   │
│  │  - Uses LLM for threat detection                        │   │
│  │  - Two-phase: detection + confirmation                  │   │
│  │  - Configurable: enabled, check_messages, check_code    │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  IntentClassifier (Abstract Base)                        │   │
│  │  - classify(message, context) -> IntentClassification   │   │
│  │  - Intent: enum of possible intents                     │   │
│  │  - Uses LLM for classification                          │   │
│  │  - Configurable: confidence_threshold, default_intent   │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                  TUTOR-SPECIFIC COMPONENTS                      │
│  (Specific to tutor agent)                                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  TutorIntentClassifier (extends IntentClassifier)        │   │
│  │  - Intents: QUESTION_EXAMPLE, QUESTION_HOWTO,           │   │
│  │            HELP_DEBUG, HELP_REVIEW, CLARIFICATION, OTHER│   │
│  │  - Prompt: tutor-specific classification prompt         │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  ResponseStrategy (Abstract Base)                        │   │
│  │  - execute(context, llm, config) -> StrategyResponse    │   │
│  │  - build_system_prompt(context) -> str                  │   │
│  │  - build_user_message(context) -> str                   │   │
│  └─────────────────────────────────────────────────────────┘   │
│           │                                                     │
│           ├── QuestionExampleStrategy                          │
│           ├── QuestionHowtoStrategy                            │
│           ├── HelpDebugStrategy                                │
│           ├── HelpReviewStrategy                               │
│           ├── ClarificationStrategy                            │
│           └── OtherStrategy                                    │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  StrategyRegistry                                        │   │
│  │  - get(intent) -> ResponseStrategy                      │   │
│  │  - Maps intents to strategy implementations             │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  TutorAgent (Orchestrator)                               │   │
│  │  - process_message(trigger, context) -> ProcessingResult│   │
│  │  - Uses: SecurityGate, IntentClassifier, StrategyRegistry │
│  │  - Handles: context building, response sending          │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Class Interfaces

#### LLMClient (Protocol)

```python
from typing import Protocol

class LLMClient(Protocol):
    """Protocol for LLM client - any provider can implement this."""

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
```

#### SecurityGate (Abstract)

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

class ThreatType(str, Enum):
    PROMPT_INJECTION = "prompt_injection"
    CREDENTIAL_EXTRACTION = "credential_extraction"
    MALICIOUS_CODE = "malicious_code"
    HARASSMENT = "harassment"
    OTHER = "other"

class ThreatLevel(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

@dataclass
class ThreatDetection:
    threat_type: ThreatType
    level: ThreatLevel
    description: str
    evidence: str | None = None
    source: str = "unknown"  # "message" or "code"

@dataclass
class SecurityCheckResult:
    is_safe: bool
    threats: list[ThreatDetection] = field(default_factory=list)
    was_confirmed: bool = False

class SecurityGate(ABC):
    """Abstract security gate - can be extended for different use cases."""

    def __init__(self, llm: LLMClient, config: SecurityConfig):
        self.llm = llm
        self.config = config

    @abstractmethod
    async def check(self, content: str, source: str) -> SecurityCheckResult:
        """Check content for security threats."""
        ...

    async def check_message(self, message: str) -> SecurityCheckResult:
        """Convenience method for checking messages."""
        return await self.check(message, source="message")

    async def check_code(self, code: str) -> SecurityCheckResult:
        """Convenience method for checking code."""
        return await self.check(code, source="code")
```

#### IntentClassifier (Abstract)

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Generic, TypeVar

IntentT = TypeVar("IntentT", bound=Enum)

@dataclass
class IntentClassification(Generic[IntentT]):
    """Result of intent classification.

    The LLM always provides user_intent_description (what the user wants).
    The intent field is None when no defined intent matches.
    """
    intent: IntentT | None              # None when no defined intent matches
    confidence: float                   # Confidence in the matched intent (0.0 if None)
    user_intent_description: str        # ALWAYS populated - LLM's description of user's request
    reasoning: str | None = None        # Why this intent was chosen (or why no match)
    secondary_intent: IntentT | None = None  # Second-best match, if any

class IntentClassifier(ABC, Generic[IntentT]):
    """Abstract intent classifier - extend for specific agent intents.

    Key design decisions:
    - 100% LLM-based classification (no rules, no keywords)
    - Always returns user_intent_description for logging/fallback
    - Returns intent=None when no defined intent matches
    - Each agent defines its own intent enum
    """

    def __init__(
        self,
        llm: LLMClient,
        confidence_threshold: float = 0.5,
    ):
        self.llm = llm
        self.confidence_threshold = confidence_threshold

    @abstractmethod
    async def classify(
        self,
        message: str,
        context: str | None = None,
    ) -> IntentClassification[IntentT]:
        """Classify the intent of a message.

        Returns IntentClassification with:
        - intent: matched intent or None
        - user_intent_description: always populated
        - confidence: 0.0-1.0 (0.0 if no match)
        """
        ...

    @abstractmethod
    def get_available_intents(self) -> list[IntentT]:
        """Return the list of intents this classifier can match."""
        ...

    @abstractmethod
    def get_classification_prompt(self, message: str, context: str | None) -> str:
        """Build the prompt for intent classification.

        The prompt should instruct the LLM to:
        1. Always describe what the user wants
        2. Try to match to one of the defined intents
        3. Return null/None if no intent matches well
        """
        ...
```

#### TutorIntentClassifier (Implementation)

```python
class TutorIntent(str, Enum):
    """Intents specific to the tutor agent."""
    QUESTION_EXAMPLE = "question_example"    # About assignment requirements
    QUESTION_HOWTO = "question_howto"        # General programming how-to
    HELP_DEBUG = "help_debug"                # Debugging assistance
    HELP_REVIEW = "help_review"              # Code review request
    CLARIFICATION = "clarification"          # Follow-up to previous answer

    # Note: No OTHER - unmatched intents return intent=None

class TutorIntentClassifier(IntentClassifier[TutorIntent]):
    """Tutor-specific intent classifier.

    Classifies student messages into predefined intents.
    When no intent matches, returns intent=None with user_intent_description.
    """

    def __init__(self, llm: LLMClient, confidence_threshold: float = 0.5):
        super().__init__(llm, confidence_threshold)

    def get_available_intents(self) -> list[TutorIntent]:
        return list(TutorIntent)

    async def classify(
        self,
        message: str,
        context: str | None = None,
    ) -> IntentClassification[TutorIntent]:
        prompt = self.get_classification_prompt(message, context)
        response = await self.llm.complete(prompt, max_tokens=400)
        return self._parse_response(response)

    def get_classification_prompt(self, message: str, context: str | None) -> str:
        # Include available intents in prompt so LLM knows what to match
        intent_descriptions = "\n".join([
            f"- {intent.value}: {self._get_intent_description(intent)}"
            for intent in self.get_available_intents()
        ])

        return TUTOR_INTENT_CLASSIFICATION_PROMPT.format(
            message=message,
            context=context or "(No previous context)",
            available_intents=intent_descriptions,
        )

    def _parse_response(self, response: str) -> IntentClassification[TutorIntent]:
        """Parse LLM JSON response into IntentClassification."""
        data = json.loads(self._extract_json(response))

        # user_intent_description is always required
        user_intent_description = data["user_intent_description"]

        # intent may be null/None if no match
        intent = None
        confidence = 0.0
        if data.get("intent"):
            intent = self._parse_intent(data["intent"])
            confidence = float(data.get("confidence", 0.5))

            # Apply threshold
            if confidence < self.confidence_threshold:
                intent = None
                confidence = 0.0

        return IntentClassification(
            intent=intent,
            confidence=confidence,
            user_intent_description=user_intent_description,
            reasoning=data.get("reasoning"),
        )
```

#### ResponseStrategy (Abstract)

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class StrategyResponse:
    message_content: str
    message_title: str | None = None
    strategy_name: str = "unknown"

class ResponseStrategy(ABC):
    """Abstract response strategy - one per intent."""

    name: str

    def __init__(self, personality_config: PersonalityConfig):
        self.personality_config = personality_config

    @abstractmethod
    async def execute(
        self,
        context: ConversationContext,
        classification: IntentClassification,
        llm: LLMClient,
        config: StrategyConfig,
    ) -> StrategyResponse:
        """Execute the strategy and generate a response.

        Args:
            context: The conversation context
            classification: Intent classification (includes user_intent_description)
            llm: LLM client for response generation
            config: Strategy-specific configuration
        """
        ...

    @abstractmethod
    def build_system_prompt(self, context: ConversationContext) -> str:
        """Build the system prompt for the LLM."""
        ...

    def build_user_message(self, context: ConversationContext) -> str:
        """Build the user message for the LLM."""
        if context.trigger_message:
            return context.trigger_message.content
        return "(No message)"


class FallbackStrategy(ResponseStrategy):
    """Handles unmatched intents using user_intent_description.

    When no predefined intent matches, this strategy uses the LLM's
    description of what the user wants to generate a helpful response.
    """

    name = "fallback"

    async def execute(
        self,
        context: ConversationContext,
        classification: IntentClassification,
        llm: LLMClient,
        config: StrategyConfig,
    ) -> StrategyResponse:
        # Use user_intent_description to understand what the student wants
        user_intent = classification.user_intent_description

        system_prompt = self.build_system_prompt(context)
        user_message = f"""The student's request: {context.trigger_message.content}

Interpreted as: {user_intent}

Please provide a helpful response based on this interpretation."""

        response = await llm.complete(
            prompt=user_message,
            system_prompt=system_prompt,
            max_tokens=config.max_tokens,
            temperature=config.temperature,
        )

        return StrategyResponse(
            message_content=response,
            strategy_name=self.name,
        )
```

### Data Flow

```
Input: Message + Context
         │
         ▼
┌─────────────────────────┐
│    SecurityGate.check() │  ← General component
│    (LLM call #1)        │
└─────────────────────────┘
         │
         ▼ (if safe)
┌─────────────────────────┐
│ IntentClassifier.classify()│  ← General interface, tutor implementation
│    (LLM call #2)        │
└─────────────────────────┘
         │
         ▼
┌─────────────────────────┐
│ StrategyRegistry.get()  │  ← Maps intent → strategy
└─────────────────────────┘
         │
         ▼
┌─────────────────────────┐
│  Strategy.execute()     │  ← Tutor-specific strategies
│    (LLM call #3)        │
└─────────────────────────┘
         │
         ▼
Output: StrategyResponse
```

---

## Next Steps

1. **Refactor code** to match this object-oriented design
2. **Extract general components** to a shared location (e.g., `computor_agent.core`)
3. **Simplify scheduler** to only poll for messages
4. **Test messaging flow** end-to-end
5. **Implement grading task separately** (see [tutor-grading.md](./tutor-grading.md))
