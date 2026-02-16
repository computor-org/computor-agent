"""
Development mode for Tutor Agent - allows testing without API calls.

This module provides a development environment where you can:
- Type messages directly into the shell
- See agent processing in real-time
- Test conversation flows without API calls
- Simulate different student contexts
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Dict, List
from pydantic import BaseModel, Field
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich import print as rprint

logger = logging.getLogger(__name__)
console = Console()


class MockMessageAuthor(BaseModel):
    """Mock message author matching API structure."""
    id: str = "dev_user"
    given_name: str = "Dev"
    family_name: str = "User"


class MockMessageAuthorCourseMember(BaseModel):
    """Mock author course member matching API structure."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    course_role_id: str = "_student"


class MockMessage(BaseModel):
    """Simulated message for development mode - Pydantic model."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    content: str = ""
    title: Optional[str] = None
    parent_id: Optional[str] = None
    submission_group_id: Optional[str] = None
    author_id: str = "dev_user"
    author: Optional[MockMessageAuthor] = Field(default_factory=MockMessageAuthor)
    author_course_member: Optional[MockMessageAuthorCourseMember] = Field(
        default_factory=MockMessageAuthorCourseMember
    )
    created_at: datetime = Field(default_factory=datetime.now)
    unread: bool = True

    def to_dict(self) -> dict:
        """Convert to dict format for agent.process_message()."""
        return {
            "id": self.id,
            "content": self.content,
            "title": self.title,
            "parent_id": self.parent_id,
            "submission_group_id": self.submission_group_id,
            "author_id": self.author_id,
            "created_at": self.created_at.isoformat(),
            "unread": self.unread,
        }


class MockSubmissionGroupMember(BaseModel):
    """Mock submission group member matching API structure."""
    user_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    course_member_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    full_name: str = "Dev User"
    username: str = "dev_user"


class MockSubmissionGroup(BaseModel):
    """Mock submission group matching API structure."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    members: List[MockSubmissionGroupMember] = Field(
        default_factory=lambda: [MockSubmissionGroupMember()]
    )
    course_id: Optional[str] = "dev_course"
    course_content_id: Optional[str] = "dev_content"


class MockCourseContent(BaseModel):
    """Simulated course content matching API structure."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: Optional[str] = "Development Assignment"
    description: Optional[str] = "Test assignment for development"
    directory: Optional[str] = "dev_assignment"
    unread_message_count: int = 0
    course_id: str = "dev_course"
    submission_group: Optional[MockSubmissionGroup] = None

    class Config:
        # Allow assignment to fields after initialization
        validate_assignment = True

    def __init__(self, **data):
        """Initialize with proper submission group."""
        # Extract submission_group_id if provided (for backwards compatibility)
        submission_group_id = data.pop('submission_group_id', None)
        super().__init__(**data)

        # Create submission group if not provided
        if not self.submission_group:
            sg_id = submission_group_id or str(uuid.uuid4())
            self.submission_group = MockSubmissionGroup(id=sg_id)


class MessageSimulator:
    """Simulates message creation and conversation threading."""

    def __init__(self):
        self.messages: Dict[str, MockMessage] = {}
        self.conversation_chains: Dict[str, List[str]] = {}  # root_id -> [message_ids]
        self.current_submission_group_id = str(uuid.uuid4())

    def create_message(
        self,
        content: str,
        title: str = "",
        parent_id: Optional[str] = None,
        add_request_tag: bool = False
    ) -> MockMessage:
        """Create a new message, optionally as part of a conversation."""
        if add_request_tag and not title:
            title = "#ai::request"
        elif add_request_tag:
            title = f"#ai::request {title}"

        message = MockMessage(
            content=content,
            title=title,
            parent_id=parent_id,
            submission_group_id=self.current_submission_group_id,
        )

        self.messages[message.id] = message

        # Track conversation chains
        if parent_id:
            # Find the root of this conversation
            root_id = self._find_conversation_root(parent_id)
            if root_id in self.conversation_chains:
                self.conversation_chains[root_id].append(message.id)
            else:
                self.conversation_chains[root_id] = [message.id]
        else:
            # This is a new root message
            self.conversation_chains[message.id] = []

        return message

    def _find_conversation_root(self, message_id: str) -> str:
        """Find the root message of a conversation chain."""
        current_id = message_id
        while current_id in self.messages:
            msg = self.messages[current_id]
            if msg.parent_id:
                current_id = msg.parent_id
            else:
                return current_id
        return message_id

    def get_conversation(self, message_id: str) -> List[MockMessage]:
        """Get all messages in a conversation chain."""
        root_id = self._find_conversation_root(message_id)
        chain = [self.messages.get(root_id)]

        if root_id in self.conversation_chains:
            for msg_id in self.conversation_chains[root_id]:
                if msg_id in self.messages:
                    chain.append(self.messages[msg_id])

        return [msg for msg in chain if msg]

    def add_ai_response(self, content: str, parent_id: str) -> MockMessage:
        """Simulate an AI response message."""
        return self.create_message(
            content=content,
            title="#ai::response",
            parent_id=parent_id,
        )


class MockComputorClient:
    """Mock client that simulates API responses without making actual calls."""

    def __init__(self, simulator: MessageSimulator):
        self.simulator = simulator
        self.messages = MockMessagesEndpoint(simulator)
        self.tutors = MockTutorsEndpoint()
        self.course_members = MockCourseMembersEndpoint()
        self.submission_groups = MockSubmissionGroupsEndpoint()
        self.submissions = MockSubmissionsEndpoint()

    async def login(self, username: str, password: str):
        """Mock login - always succeeds."""
        logger.info(f"Mock login as {username}")

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class MockMessageResponse(BaseModel):
    """Mock message response object matching API structure."""
    id: str
    content: str = ""
    title: Optional[str] = None
    parent_id: Optional[str] = None


class MockMessagesEndpoint:
    """Mock messages API endpoint."""

    def __init__(self, simulator: MessageSimulator):
        self.simulator = simulator

    async def list(self, **kwargs) -> List[MockMessage]:
        """List messages matching filters. Returns MockMessage objects (not dicts)."""
        messages = []
        for msg in self.simulator.messages.values():
            # Apply filters
            if kwargs.get("submission_group_id") and msg.submission_group_id != kwargs["submission_group_id"]:
                continue
            if kwargs.get("unread") and not msg.unread:
                continue
            if kwargs.get("tags"):
                tags = kwargs["tags"]
                if not any(tag in (msg.title or "") for tag in tags):
                    continue

            messages.append(msg)  # Return the object, not dict

        return messages

    async def get(self, id: str) -> MockMessage:
        """Get a specific message. Returns MockMessage object."""
        if id in self.simulator.messages:
            return self.simulator.messages[id]  # Return the object, not dict
        raise ValueError(f"Message {id} not found")

    async def create(self, data: Dict) -> MockMessageResponse:
        """Create a new message (for AI responses) - returns object with id attribute."""
        message = MockMessage(
            content=data.get("content", ""),
            title=data.get("title", ""),
            parent_id=data.get("parent_id"),
            submission_group_id=data.get("submission_group_id", self.simulator.current_submission_group_id),
        )
        self.simulator.messages[message.id] = message

        # Display the AI response
        console.print(Panel(
            f"[bold cyan]AI Response:[/bold cyan]\n\n{message.content}",
            title=f"Response (replying to {message.parent_id[:8]}...)" if message.parent_id else "Response",
            border_style="cyan"
        ))

        # Return an object with id attribute, not a dict
        return MockMessageResponse(
            id=message.id,
            content=message.content,
            title=message.title,
            parent_id=message.parent_id
        )

    async def reads(self, id: str):
        """Mark message as read."""
        if id in self.simulator.messages:
            self.simulator.messages[id].unread = False
            logger.debug(f"Marked message {id} as read")


class MockTutorsEndpoint:
    """Mock tutors API endpoint."""

    async def get_course_members(self) -> List[Dict]:
        """Get course members list."""
        return [{
            "id": "dev_member_1",
            "course_id": "dev_course",
            "unread_message_count": 1,
        }]

    async def get_course_member_id_course_contents(self, member_id: str) -> List[Dict]:
        """Get course contents for a member."""
        return [{
            "id": "dev_content_1",
            "title": "Development Assignment",
            "unread_message_count": 1,
            "submission_group": {
                "id": "dev_sg_1"
            }
        }]

    async def get_course_members_course_contents(self, member_id: str, content_id: str) -> Dict:
        """Get detailed course content."""
        return {
            "id": content_id,
            "title": "Development Assignment",
            "directory": "dev_assignment",
            "submission_group": {
                "id": "dev_sg_1"
            },
            "unread_message_count": 1,
        }

    async def course_contents_description(self, **kwargs) -> None:
        """Mock description endpoint - no data in dev mode."""
        return None

    async def course_contents_reference(self, **kwargs) -> None:
        """Mock reference endpoint - no data in dev mode."""
        return None


class MockCourseMembersEndpoint:
    """Mock course members endpoint."""

    async def get(self, id: str) -> Dict:
        """Get course member details."""
        return {
            "id": id,
            "user": {
                "id": "dev_user",
                "name": "Developer",
            },
            "role": "_student",
        }


class MockSubmissionGroupsEndpoint:
    """Mock submission groups endpoint."""
    pass


class MockSubmissionsEndpoint:
    """Mock submissions endpoint - no real downloads in dev mode."""

    async def artifacts_download(self, **kwargs) -> None:
        """Mock artifact download - no data in dev mode."""
        return None

    async def get_artifacts(self, **kwargs) -> list:
        """Mock artifact listing - no data in dev mode."""
        return []

    async def get_artifacts_download(self, *args, **kwargs) -> None:
        """Mock artifact download by ID - no data in dev mode."""
        return None


def _ensure_prompt_files(prompts_dir: Path) -> None:
    """
    Ensure all required prompt files exist in the directory.

    Creates missing files with default content but doesn't overwrite existing ones.

    Args:
        prompts_dir: Directory to check/create prompt files in
    """
    from computor_agent.tutor.prompts.templates import (
        PERSONALITY_PROMPTS,
        STRATEGY_PROMPTS,
        SECURITY_DETECTION_PROMPT,
        SECURITY_CONFIRMATION_PROMPT,
    )

    # Create directory structure
    personality_dir = prompts_dir / "personality"
    strategy_dir = prompts_dir / "strategy"
    security_dir = prompts_dir / "security"

    for dir_path in [personality_dir, strategy_dir, security_dir]:
        dir_path.mkdir(parents=True, exist_ok=True)

    initialized_count = 0

    # Check and create personality prompts
    for tone, content in PERSONALITY_PROMPTS.items():
        file_path = personality_dir / f"{tone}.md"
        if not file_path.exists():
            _write_prompt_file(file_path, content, f"Personality: {tone}")
            initialized_count += 1
            logger.debug(f"Created prompt file: {file_path}")

    # Check and create strategy prompts
    for strategy, content in STRATEGY_PROMPTS.items():
        file_path = strategy_dir / f"{strategy}.md"
        if not file_path.exists():
            _write_prompt_file(file_path, content, f"Strategy: {strategy}")
            initialized_count += 1
            logger.debug(f"Created prompt file: {file_path}")

    # Check and create security prompts
    security_prompts = {
        "detection": SECURITY_DETECTION_PROMPT,
        "confirmation": SECURITY_CONFIRMATION_PROMPT,
    }

    for name, content in security_prompts.items():
        file_path = security_dir / f"{name}.md"
        if not file_path.exists():
            _write_prompt_file(file_path, content, f"Security: {name}")
            initialized_count += 1
            logger.debug(f"Created prompt file: {file_path}")

    # Copy documentation files
    import shutil
    docs_to_copy = [
        ("PROMPT_ENGINEERING_GUIDE.md", "README.md"),
        ("VARIABLE_REFERENCE.md", "VARIABLES.md"),
    ]

    for source_name, dest_name in docs_to_copy:
        source = Path(__file__).parent / "prompts" / source_name
        dest = prompts_dir / dest_name

        if source.exists() and not dest.exists():
            try:
                shutil.copy2(source, dest)
                console.print(f"[green]✓ Copied {dest_name} documentation[/green]")
            except Exception as e:
                logger.warning(f"Could not copy {source_name}: {e}")

    if initialized_count > 0:
        console.print(f"[green]✓ Initialized {initialized_count} missing prompt files[/green]")


def _write_prompt_file(file_path: Path, content: str, title: str = "") -> None:
    """
    Write a prompt to a markdown file with frontmatter.

    Args:
        file_path: Path to write to
        content: Prompt content
        title: Title for frontmatter
    """
    frontmatter = f"""---
title: {title}
generated: true
editable: true
---

"""
    full_content = frontmatter + content
    file_path.write_text(full_content)


class DevelopmentScheduler:
    """Interactive scheduler for development mode."""

    def __init__(self, agent, simulator: MessageSimulator, assignment_context=None):
        self.agent = agent
        self.simulator = simulator
        self.assignment_context = assignment_context
        self.running = False

    async def start(self):
        """Start the interactive development loop."""
        self.running = True

        last_message_id = None

        while self.running:
            try:
                # Get user input
                user_input = Prompt.ask("\n[bold blue]You[/bold blue]")

                if user_input.startswith("/"):
                    # Handle commands
                    await self._handle_command(user_input, last_message_id)
                    if not self.running:
                        break
                    continue

                # Create a new message with AI request tag
                message = self.simulator.create_message(
                    content=user_input,
                    add_request_tag=True,
                    parent_id=last_message_id if last_message_id else None
                )

                # Display user message
                console.print(f"[dim]Message ID: {message.id[:8]}...[/dim]")

                # Process the message through the agent
                await self._process_message(message)

                # Update last message for potential follow-ups
                last_message_id = message.id

            except KeyboardInterrupt:
                console.print("\n[yellow]Interrupted. Type /exit to quit.[/yellow]")
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")
                logger.exception("Error in development loop")

    async def _handle_command(self, command: str, last_message_id: Optional[str]):
        """Handle special commands."""
        parts = command.split()
        cmd = parts[0].lower()

        if cmd == "/exit":
            console.print("[yellow]Exiting development mode...[/yellow]")
            self.running = False

        elif cmd == "/new":
            console.print("[green]Starting new conversation (next message will have #ai::request tag)[/green]")

        elif cmd == "/reply" and len(parts) > 1:
            msg_id = parts[1]
            if msg_id in self.simulator.messages:
                console.print(f"[green]Replying to message {msg_id}[/green]")
            else:
                console.print(f"[red]Message {msg_id} not found[/red]")

        elif cmd == "/show":
            self._show_conversation_history()

        elif cmd == "/clear":
            self.simulator.messages.clear()
            self.simulator.conversation_chains.clear()
            console.print("[yellow]All messages cleared[/yellow]")

        elif cmd == "/reload":
            # Manually reload all prompts
            from computor_agent.tutor.prompts.loader import get_prompt_loader
            loader = get_prompt_loader()
            loader.load_all()
            console.print("[green]✅ All prompts reloaded[/green]")

        elif cmd == "/assignment":
            self._show_assignment_details()

        else:
            console.print(f"[red]Unknown command: {cmd}[/red]")

    def _show_assignment_details(self):
        """Display assignment details if loaded."""
        if not self.assignment_context:
            console.print("[yellow]No assignment loaded. Use --reference and --assignment flags.[/yellow]")
            return

        ctx = self.assignment_context
        console.print(Panel(
            f"[bold]{ctx.title}[/bold]\n\n"
            f"Identifier: [cyan]{ctx.identifier}[/cyan]\n"
            f"Language: {ctx.language}\n"
            f"Slug: {ctx.slug}\n\n"
            f"[bold]Files:[/bold]\n" +
            "\n".join(f"  • {f.path} {'[submission]' if f.is_submission_file else ''}" for f in ctx.files) +
            f"\n\n[bold]Description:[/bold]\n{ctx.readme_content[:500]}{'...' if len(ctx.readme_content) > 500 else ''}",
            title="Assignment Details",
            border_style="cyan"
        ))

    def _show_conversation_history(self):
        """Display the conversation history."""
        if not self.simulator.messages:
            console.print("[yellow]No messages yet[/yellow]")
            return

        table = Table(title="Conversation History")
        table.add_column("ID", style="cyan")
        table.add_column("Author", style="green")
        table.add_column("Title", style="yellow")
        table.add_column("Content", style="white", overflow="fold", max_width=50)
        table.add_column("Parent", style="dim")

        for msg in self.simulator.messages.values():
            author_name = f"{msg.author.given_name} {msg.author.family_name}" if msg.author else "Unknown"
            table.add_row(
                msg.id[:8] + "...",
                author_name,
                msg.title or "(no title)",
                msg.content[:100] + "..." if len(msg.content) > 100 else msg.content,
                msg.parent_id[:8] + "..." if msg.parent_id else "-"
            )

        console.print(table)

    async def _process_message(self, message: MockMessage):
        """Process a message through the agent."""
        console.print("[dim]Processing message...[/dim]")

        # Create mock course content with assignment info if available
        if self.assignment_context:
            course_content = MockCourseContent(
                submission_group_id=message.submission_group_id,
                unread_message_count=1,
                title=self.assignment_context.title,
                description=self.assignment_context.readme_content,
                directory=self.assignment_context.identifier,
            )
        else:
            course_content = MockCourseContent(
                submission_group_id=message.submission_group_id,
                unread_message_count=1
            )

        try:
            # Process through the agent
            result = await self.agent.process_message(
                submission_group_id=message.submission_group_id,
                message=message.to_dict(),
                repository_path=None,  # No repo in dev mode
                reference_path=None,
                send_response=True,
                reply_to_message_id=message.id,
                course_content=course_content,
                course_member_id="dev_member_1",
                assignment_context=self.assignment_context,  # Pass assignment context
            )

            # Display processing results
            if result.success:
                if result.blocked_by_security:
                    console.print("[bold red]Message blocked by security![/bold red]")
                elif result.message_sent:
                    console.print(f"[green]✓ Response sent[/green]")
                else:
                    console.print(f"[yellow]No response sent[/yellow]")

                if result.intent:
                    console.print(f"[dim]Intent: {result.intent.intent.value if result.intent.intent else 'unknown'}[/dim]")
                    console.print(f"[dim]User wants: {result.intent.user_intent_description}[/dim]")
            else:
                console.print(f"[red]Processing failed: {result.error}[/red]")

        except Exception as e:
            console.print(f"[red]Error processing message: {e}[/red]")
            logger.exception("Failed to process message")


async def run_development_mode(
    config_path: Path,
    verbose: bool = False,
    prompts_dir: Optional[Path] = None,
    assignment_path: Optional[Path] = None,
):
    """
    Run the tutor agent in development mode.

    This mode allows interactive testing without API calls.
    Features hot reload for prompt files.

    Args:
        config_path: Path to configuration file
        verbose: Enable verbose logging
        prompts_dir: Directory for prompt files (default: ~/.computor/prompts)
        assignment_path: Path to assignment directory (must contain meta.yaml)
    """
    from computor_agent.settings import ComputorConfig
    from computor_agent.llm.config import LLMConfig, ProviderType
    from computor_agent.llm.factory import get_provider
    from computor_agent.tutor import TutorAgent, TutorLLMAdapter
    from computor_agent.tutor.prompts.loader import get_prompt_loader
    from computor_agent.tutor.assignment_loader import AssignmentLoader, AssignmentContext

    # Load configuration
    logger.info(f"Loading config from {config_path}")
    computor_config = ComputorConfig.from_file(config_path)
    tutor_config = computor_config.get_tutor_config()

    # Load assignment context if provided
    assignment_context: Optional[AssignmentContext] = None
    if assignment_path:
        try:
            assignment_context = AssignmentLoader.load_from_path(assignment_path)
            console.print(f"[green]✓ Loaded assignment: {assignment_context.title}[/green]")
            console.print(f"[dim]  Files: {', '.join(f.path for f in assignment_context.files)}[/dim]")
        except Exception as e:
            console.print(f"[red]Failed to load assignment: {e}[/red]")

    # Setup prompt hot reload callback
    def on_prompt_reload(filename: str):
        """Callback when a prompt file is reloaded."""
        console.print(f"[yellow]🔄 Prompt reloaded: {filename}[/yellow]")

    # Determine prompts directory
    if prompts_dir is None:
        prompts_dir = Path.home() / ".computor" / "prompts"
    else:
        prompts_dir = Path(prompts_dir).expanduser().resolve()

    # Auto-initialize missing prompt files
    _ensure_prompt_files(prompts_dir)

    console.print(f"[dim]Loading prompts from: {prompts_dir}[/dim]")

    prompt_loader = get_prompt_loader(
        prompts_dir=prompts_dir,
        enable_hot_reload=True,
        reload_callback=on_prompt_reload,
        force_reload=True
    )

    # Create LLM provider
    if not computor_config.llm:
        console.print("[bold red]Error:[/bold red] LLM configuration is required")
        return

    llm_config = LLMConfig(
        provider=ProviderType(computor_config.llm.provider),
        model=computor_config.llm.model,
        base_url=computor_config.llm.base_url,
        api_key=computor_config.llm.get_api_key(),
        temperature=computor_config.llm.temperature,
    )
    llm_provider = get_provider(llm_config)
    tutor_llm = TutorLLMAdapter(llm_provider)

    # Create simulator and mock client
    simulator = MessageSimulator()
    mock_client = MockComputorClient(simulator)

    # Create the tutor agent with mock client
    agent = TutorAgent(
        config=tutor_config,
        llm=tutor_llm,
        client=mock_client,
    )

    # Build info panel
    info_lines = [
        "[bold green]Development Mode with Hot Reload[/bold green]\n",
        f"LLM: [green]{computor_config.llm.provider}[/green] ([green]{computor_config.llm.model}[/green])",
        f"Prompts directory: [cyan]{prompts_dir}[/cyan]",
        "Hot reload: [green]Enabled[/green] - Edit .md files to see changes instantly",
    ]

    if assignment_context:
        info_lines.append(f"\nAssignment: [cyan]{assignment_context.title}[/cyan]")
        info_lines.append(f"  Identifier: [dim]{assignment_context.identifier}[/dim]")
        info_lines.append(f"  Files: [dim]{', '.join(f.path for f in assignment_context.files)}[/dim]")

    info_lines.extend([
        "\nCommands:",
        "  [yellow]/new[/yellow] - Start a new conversation",
        "  [yellow]/show[/yellow] - Show conversation history",
        "  [yellow]/assignment[/yellow] - Show assignment details",
        "  [yellow]/reload[/yellow] - Manually reload all prompts",
        "  [yellow]/exit[/yellow] - Exit development mode",
    ])

    console.print(Panel(
        "\n".join(info_lines),
        title="Tutor Agent Development Mode",
        border_style="green"
    ))

    scheduler = DevelopmentScheduler(agent, simulator, assignment_context)

    try:
        await scheduler.start()
    except KeyboardInterrupt:
        console.print("\n[yellow]Development mode stopped.[/yellow]")
    finally:
        # Stop watching files
        prompt_loader.stop_watching()