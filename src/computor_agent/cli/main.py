"""
MVP CLI for computor-agent.

A simple interactive CLI for testing LLM providers, similar to codex-cli.
Supports both complete and streaming modes.
"""

import asyncio
import logging
import os
import signal
import sys
from pathlib import Path
from typing import Optional

import click
from dotenv import load_dotenv
from rich.console import Console
from rich.logging import RichHandler
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.syntax import Syntax

from computor_agent.llm.config import LLMConfig, ProviderType
from computor_agent.llm.exceptions import LLMError
from computor_agent.llm.factory import create_provider, get_provider, list_providers

# Load environment variables
load_dotenv()

console = Console()


def setup_logging(verbose: bool = False) -> None:
    """Setup rich logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True)],
    )
    # Reduce noise from third-party libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("watchdog").setLevel(logging.WARNING)
    logging.getLogger("watchdog.observers.inotify_buffer").setLevel(logging.WARNING)


def get_default_base_url(provider: str) -> str:
    """Get default base URL for a provider."""
    defaults = {
        "lmstudio": "http://localhost:1234/v1",
        "ollama": "http://localhost:11434/v1",
        "openai": "https://api.openai.com/v1",
        "dummy": "",
    }
    return defaults.get(provider, "http://localhost:1234/v1")


@click.group()
@click.version_option(version="0.1.0")
def cli():
    """Computor Agent CLI - AI assistant for course management."""
    pass


@cli.command()
@click.option(
    "--provider",
    "-p",
    type=click.Choice(list_providers()),
    default="lmstudio",
    help="LLM provider to use",
)
@click.option(
    "--model",
    "-m",
    default="gpt-oss-120b",
    help="Model name/identifier",
)
@click.option(
    "--base-url",
    "-u",
    default=None,
    help="API base URL (defaults based on provider)",
)
@click.option(
    "--temperature",
    "-t",
    type=click.FloatRange(0.0, 2.0),
    default=0.7,
    help="Sampling temperature (0.0-2.0)",
)
@click.option(
    "--max-tokens",
    type=int,
    default=None,
    help="Maximum tokens to generate",
)
@click.option(
    "--stream/--no-stream",
    "-s",
    default=True,
    help="Stream responses (default: stream)",
)
@click.option(
    "--system",
    default=None,
    help="System prompt to use",
)
def chat(
    provider: str,
    model: str,
    base_url: Optional[str],
    temperature: float,
    max_tokens: Optional[int],
    stream: bool,
    system: Optional[str],
):
    """
    Interactive chat with an LLM.

    Start an interactive chat session with the configured LLM provider.
    Type 'exit' or 'quit' to end the session.

    Examples:

        # Use LM Studio with default model
        computor-agent chat

        # Use Ollama with devstral
        computor-agent chat -p ollama -m devstral-small

        # Use with custom URL
        computor-agent chat -u http://192.168.1.100:1234/v1

        # Disable streaming
        computor-agent chat --no-stream
    """
    # Resolve base URL
    if base_url is None:
        base_url = get_default_base_url(provider)

    # Get API key from environment if needed
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY")

    config = LLMConfig(
        provider=ProviderType(provider),
        model=model,
        base_url=base_url,
        api_key=api_key,
        temperature=temperature,
        max_tokens=max_tokens,
        system_prompt=system,
    )

    console.print(
        Panel(
            f"[bold cyan]Computor Agent Chat[/bold cyan]\n\n"
            f"Provider: [green]{provider}[/green]\n"
            f"Model: [green]{model}[/green]\n"
            f"URL: [green]{base_url}[/green]\n"
            f"Streaming: [green]{stream}[/green]\n\n"
            f"Type [yellow]exit[/yellow] or [yellow]quit[/yellow] to end session.\n"
            f"Type [yellow]/help[/yellow] for commands.",
            title="Welcome",
        )
    )

    asyncio.run(_chat_loop(config, stream))


async def _chat_loop(config: LLMConfig, stream: bool):
    """Main chat loop."""
    provider = get_provider(config)

    try:
        while True:
            try:
                # Get user input
                user_input = Prompt.ask("\n[bold blue]You[/bold blue]")

                if not user_input.strip():
                    continue

                # Handle commands
                if user_input.lower() in ("exit", "quit", "/exit", "/quit"):
                    console.print("[yellow]Goodbye![/yellow]")
                    break

                if user_input.lower() in ("/help", "help"):
                    _show_help()
                    continue

                if user_input.lower() in ("/models", "/list"):
                    await _list_models(provider)
                    continue

                if user_input.lower().startswith("/system "):
                    new_system = user_input[8:].strip()
                    config = config.with_overrides(system_prompt=new_system)
                    provider = get_provider(config)
                    console.print(f"[green]System prompt updated.[/green]")
                    continue

                if user_input.lower() == "/stream":
                    stream = not stream
                    console.print(f"[green]Streaming: {stream}[/green]")
                    continue

                # Generate response
                console.print("\n[bold green]Assistant[/bold green]")

                if stream:
                    await _stream_response(provider, user_input)
                else:
                    await _complete_response(provider, user_input)

            except KeyboardInterrupt:
                console.print("\n[yellow]Interrupted. Type 'exit' to quit.[/yellow]")
                continue

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise
    finally:
        await provider.close()


async def _stream_response(provider, prompt: str):
    """Stream a response from the provider."""
    try:
        full_response = ""
        async for chunk in provider.stream(prompt):
            console.print(chunk.content, end="")
            full_response += chunk.content
        console.print()  # Newline at end
    except LLMError as e:
        console.print(f"\n[bold red]LLM Error:[/bold red] {e}")


async def _complete_response(provider, prompt: str):
    """Get a complete response from the provider."""
    try:
        with console.status("[bold green]Thinking..."):
            response = await provider.complete(prompt)

        # Try to render as markdown
        try:
            md = Markdown(response.content)
            console.print(md)
        except Exception:
            console.print(response.content)

        # Show token usage if available
        if response.usage:
            tokens = response.total_tokens or "?"
            console.print(f"\n[dim]Tokens: {tokens}[/dim]")

    except LLMError as e:
        console.print(f"[bold red]LLM Error:[/bold red] {e}")


async def _list_models(provider):
    """List available models."""
    try:
        # Check if provider supports listing models
        if hasattr(provider, "list_models"):
            with console.status("[bold green]Fetching models..."):
                models = await provider.list_models()

            console.print("\n[bold]Available Models:[/bold]")
            for model in models:
                model_id = model.get("id", str(model))
                console.print(f"  • {model_id}")
        else:
            console.print("[yellow]This provider doesn't support listing models.[/yellow]")
    except LLMError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")


def _show_help():
    """Show help message."""
    help_text = """
[bold]Commands:[/bold]
  /help      - Show this help message
  /models    - List available models
  /stream    - Toggle streaming mode
  /system <prompt> - Set system prompt
  /exit      - Exit the chat

[bold]Tips:[/bold]
  • Use streaming mode for real-time output
  • Set a system prompt to customize behavior
  • Press Ctrl+C to interrupt generation
"""
    console.print(Panel(help_text, title="Help"))


@cli.command()
@click.argument("prompt")
@click.option(
    "--provider",
    "-p",
    type=click.Choice(list_providers()),
    default="lmstudio",
    help="LLM provider to use",
)
@click.option(
    "--model",
    "-m",
    default="gpt-oss-120b",
    help="Model name/identifier",
)
@click.option(
    "--base-url",
    "-u",
    default=None,
    help="API base URL",
)
@click.option(
    "--stream/--no-stream",
    "-s",
    default=False,
    help="Stream response",
)
@click.option(
    "--system",
    default=None,
    help="System prompt",
)
def ask(
    prompt: str,
    provider: str,
    model: str,
    base_url: Optional[str],
    stream: bool,
    system: Optional[str],
):
    """
    Ask a single question and get a response.

    Examples:

        computor-agent ask "What is Python?"

        computor-agent ask "Explain async/await" --stream

        computor-agent ask "Write hello world" -p ollama -m devstral-small
    """
    if base_url is None:
        base_url = get_default_base_url(provider)

    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY")

    config = LLMConfig(
        provider=ProviderType(provider),
        model=model,
        base_url=base_url,
        api_key=api_key,
        system_prompt=system,
    )

    asyncio.run(_single_query(config, prompt, stream))


async def _single_query(config: LLMConfig, prompt: str, stream: bool):
    """Execute a single query."""
    provider = get_provider(config)

    try:
        if stream:
            async for chunk in provider.stream(prompt):
                print(chunk.content, end="", flush=True)
            print()
        else:
            response = await provider.complete(prompt)
            print(response.content)
    except LLMError as e:
        console.print(f"[bold red]Error:[/bold red] {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        await provider.close()


@cli.command()
@click.option(
    "--provider",
    "-p",
    type=click.Choice(list_providers()),
    default="lmstudio",
    help="LLM provider to use",
)
@click.option(
    "--base-url",
    "-u",
    default=None,
    help="API base URL",
)
def models(provider: str, base_url: Optional[str]):
    """
    List available models from the provider.

    Examples:

        computor-agent models

        computor-agent models -p ollama
    """
    if base_url is None:
        base_url = get_default_base_url(provider)

    config = LLMConfig(
        provider=ProviderType(provider),
        model="",  # Not needed for listing
        base_url=base_url,
    )

    asyncio.run(_list_models_cmd(config))


async def _list_models_cmd(config: LLMConfig):
    """List models command."""
    provider = get_provider(config)

    try:
        if hasattr(provider, "list_models"):
            models = await provider.list_models()
            for model in models:
                model_id = model.get("id", str(model))
                print(model_id)
        else:
            console.print("[yellow]This provider doesn't support listing models.[/yellow]")
    except LLMError as e:
        console.print(f"[bold red]Error:[/bold red] {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        await provider.close()


@cli.command()
def providers():
    """List available LLM providers."""
    console.print("[bold]Available Providers:[/bold]")
    for p in list_providers():
        default_url = get_default_base_url(p)
        console.print(f"  • [green]{p}[/green] - {default_url}")


@cli.group()
def tutor():
    """
    Tutor AI agent commands.

    The tutor agent can respond to student messages and grade submissions.

    Subcommands:
        messaging  - Interactive messaging mode (respond to student questions)
        grading    - Grade student submissions
    """
    pass


@tutor.command()
@click.option(
    "--config",
    "-c",
    type=click.Path(),
    default=None,
    help="Path to config file (default: config.yaml). Optional in dev mode.",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Enable verbose logging",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Don't send responses, just log what would happen",
)
@click.option(
    "--dev",
    is_flag=True,
    help="Run in development mode (no API calls, interactive shell)",
)
@click.option(
    "--prompts-dir",
    type=click.Path(),
    default=None,
    help="Directory for prompt markdown files (default: ~/.computor/prompts).",
)
@click.option(
    "--assignment",
    type=click.Path(exists=True),
    default=None,
    help="[Dev mode] Path to assignment directory (must contain meta.yaml).",
)
def messaging(
    config: Optional[str],
    verbose: bool,
    dry_run: bool,
    dev: bool,
    prompts_dir: Optional[str],
    assignment: Optional[str],
):
    """
    Start the messaging tutor agent.

    Polls for student messages with trigger tags and responds automatically.

    Examples:

        # Start messaging agent
        computor-agent tutor messaging

        # Development mode (interactive, no API calls)
        computor-agent tutor messaging --dev

        # Dev mode with assignment context
        computor-agent tutor messaging --dev --assignment ./my-assignment
    """
    setup_logging(verbose)
    logger = logging.getLogger(__name__)

    # Resolve config path: try explicit, then config.yaml, then example.yaml
    if config is not None:
        config_path = Path(config)
        if not config_path.exists():
            console.print(f"[bold red]Error:[/bold red] Config file '{config}' does not exist.")
            sys.exit(1)
    else:
        if Path("config.yaml").exists():
            config_path = Path("config.yaml")
        elif Path("example.yaml").exists():
            config_path = Path("example.yaml")
        elif dev:
            config_path = None  # type: ignore[assignment]
        else:
            console.print(
                "[bold red]Error:[/bold red] No config file found. "
                "Create a config.yaml or pass one with -c."
            )
            sys.exit(1)

    # Check if running in development mode
    if dev:
        from computor_agent.tutor.dev_mode import run_development_mode
        prompts_path = Path(prompts_dir) if prompts_dir else None
        assignment_path = Path(assignment) if assignment else None
        asyncio.run(run_development_mode(
            config_path,
            verbose,
            prompts_path,
            assignment_path=assignment_path,
        ))
        return

    try:
        from computor_agent.settings import ComputorConfig

        logger.info(f"Loading config from {config_path}")
        computor_config = ComputorConfig.from_file(config_path)

        tutor_config = computor_config.get_tutor_config()
        git_credentials = computor_config.get_credentials_store()

        logger.info(f"Git credentials: {len(git_credentials)} mapping(s)")

    except FileNotFoundError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        sys.exit(1)
    except Exception as e:
        console.print(f"[bold red]Configuration error:[/bold red] {e}")
        sys.exit(1)

    console.print(
        Panel(
            f"[bold cyan]Tutor AI Agent - Messaging[/bold cyan]\n\n"
            f"Backend: [green]{computor_config.backend.url}[/green]\n"
            f"Auth: [green]{computor_config.backend.auth_method}[/green]\n"
            f"LLM: [green]{computor_config.llm.provider if computor_config.llm else 'not configured'}[/green] "
            f"([green]{computor_config.llm.model if computor_config.llm else 'n/a'}[/green])\n"
            f"Git credentials: [green]{len(git_credentials)} mapping(s)[/green]\n"
            f"Dry run: [yellow]{dry_run}[/yellow]\n\n"
            f"Press [yellow]Ctrl+C[/yellow] to stop.",
            title="Starting",
        )
    )

    prompts_path = Path(prompts_dir) if prompts_dir else None
    asyncio.run(_run_tutor_messaging(computor_config, tutor_config, git_credentials, dry_run, prompts_path))


@tutor.command()
@click.option(
    "--config",
    "-c",
    type=click.Path(exists=True),
    default="config.yaml",
    help="Path to config file (default: config.yaml).",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Enable verbose logging",
)
@click.option(
    "--dev",
    is_flag=True,
    help="Run in development mode (local files, no API calls)",
)
@click.option(
    "--prompts-dir",
    type=click.Path(),
    default=None,
    help="Directory for prompt markdown files (default: ~/.computor/prompts).",
)
@click.option(
    "--reference",
    type=click.Path(exists=True),
    required=False,
    help="[Dev mode] Path to reference solution directory (must contain meta.yaml).",
)
@click.option(
    "--student",
    type=click.Path(exists=True),
    required=False,
    help="[Dev mode] Path to student submission directory.",
)
@click.option(
    "--language",
    "-l",
    default=None,
    help="Language for assignment description (e.g., 'en', 'de').",
)
def grading(
    config: str,
    verbose: bool,
    dev: bool,
    prompts_dir: Optional[str],
    reference: Optional[str],
    student: Optional[str],
    language: Optional[str],
):
    """
    Grade student submissions.

    In dev mode: Grade a local submission against a reference solution.
    In production mode: Poll for submissions that need grading.

    Examples:

        # Dev mode - grade local files
        computor-agent tutor grading --dev --reference ./assignment --student ./submission

        # Production mode (not yet implemented)
        computor-agent tutor grading
    """
    setup_logging(verbose)

    config_path = Path(config)

    if dev:
        if not reference or not student:
            console.print("[bold red]Error:[/bold red] --reference and --student are required in dev mode")
            console.print("\nUsage: computor-agent tutor grading --dev --reference ./assignment --student ./submission")
            sys.exit(1)

        from computor_agent.tutor.grading.dev_mode import run_grading_dev_mode

        reference_path = Path(reference)
        student_path = Path(student)
        prompts_path = Path(prompts_dir) if prompts_dir else None

        asyncio.run(run_grading_dev_mode(
            config_path,
            reference_path,
            student_path,
            verbose=verbose,
            language=language,
            prompts_dir=prompts_path,
        ))
        return

    # Production mode - not yet fully implemented
    console.print("[yellow]Production grading mode is not yet implemented.[/yellow]")
    console.print("Use --dev mode for local testing:")
    console.print("  computor-agent tutor grading --dev --reference ./assignment --student ./submission")


async def _run_tutor_messaging(computor_config, tutor_config, git_credentials, dry_run: bool, prompts_dir: Optional[Path] = None):
    """Run the tutor messaging agent."""
    from computor_client import ComputorClient

    from computor_agent.llm.config import LLMConfig, ProviderType
    from computor_agent.llm.factory import get_provider
    from computor_agent.tutor import TutorAgent, TutorScheduler, SchedulerConfig, TutorLLMAdapter
    from computor_agent.tutor.prompts.loader import get_prompt_loader

    logger = logging.getLogger(__name__)

    # Initialize prompt loader only if prompts_dir is specified
    if prompts_dir is not None:
        prompts_dir = Path(prompts_dir).expanduser().resolve()

        # Auto-initialize missing files when directory is explicitly specified
        from computor_agent.tutor.dev_mode import _ensure_prompt_files
        _ensure_prompt_files(prompts_dir)

        logger.info(f"Loading prompts from: {prompts_dir}")
        prompt_loader = get_prompt_loader(
            prompts_dir=prompts_dir,
            enable_hot_reload=False,  # No hot reload in production
            force_reload=True
        )
    else:
        # No prompts directory specified - will use hardcoded templates
        logger.info("Using built-in prompt templates")

    # Create LLM provider
    if not computor_config.llm:
        console.print("[bold red]Error:[/bold red] LLM configuration is required")
        sys.exit(1)

    llm_config = LLMConfig(
        provider=ProviderType(computor_config.llm.provider),
        model=computor_config.llm.model,
        base_url=computor_config.llm.base_url,
        api_key=computor_config.llm.get_api_key(),
        temperature=computor_config.llm.temperature,
    )
    llm_provider = get_provider(llm_config)

    # Verify the LLM model is reachable and working before accepting student messages
    console.print(f"[dim]Checking LLM connectivity ({llm_config.provider.value}/{llm_config.model})...[/dim]")
    try:
        await llm_provider.check_health()
        console.print("[green]LLM is ready.[/green]")
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] LLM health check failed: {e}")
        console.print("[dim]Make sure your LLM server is running and the model is available.[/dim]")
        sys.exit(1)

    tutor_llm = TutorLLMAdapter(llm_provider)

    # Create Computor client with appropriate authentication
    client_kwargs = {"base_url": computor_config.backend.url}

    if computor_config.backend.auth_method == "api_token":
        # Use X-API-Token header for API token auth
        client_kwargs["headers"] = {
            "X-API-Token": computor_config.backend.get_api_token()
        }
        logger.info("Using API token authentication")

    async with ComputorClient(**client_kwargs) as client:
        # Authenticate with username/password if not using API token
        if computor_config.backend.auth_method != "api_token":
            try:
                await client.login(
                    username=computor_config.backend.username,
                    password=computor_config.backend.get_password(),
                )
                logger.info("Authenticated with username/password")
            except Exception as e:
                console.print(f"[bold red]Authentication failed:[/bold red] {e}")
                sys.exit(1)

        # Create tutor agent (uses ComputorClient directly)
        agent = TutorAgent(
            config=tutor_config,
            llm=tutor_llm,
            client=client,
        )

        # Create scheduler config from tutor config or defaults
        if tutor_config.scheduler:
            scheduler_config = SchedulerConfig.model_validate(tutor_config.scheduler)
            logger.info(f"Scheduler config: poll={scheduler_config.poll_interval_seconds}s, cache={scheduler_config.cache.enabled}")
        else:
            scheduler_config = SchedulerConfig()
            logger.info("Using default scheduler config")

        # Message trigger callback for HTTP polling scheduler
        async def on_message_trigger_polling(result, course_content):
            """
            Handle message trigger from HTTP polling scheduler.

            Args:
                result: TriggerCheckResult with message_trigger
                course_content: CourseContentStudentGet from scheduler
            """
            logger.info(f"Processing message trigger: {result.reason}")
            if dry_run:
                logger.info(f"[DRY RUN] Would process message: {result.message_trigger.message_id}")
                return

            # Get the message data
            message = {
                "id": result.message_trigger.message_id,
                "content": result.message_trigger.content,
                "title": result.message_trigger.title,
                "author_id": result.message_trigger.author_id,
            }

            # Get submission_group_id from the course content
            sg = course_content.submission_group
            submission_group_id = sg.id if sg else result.message_trigger.submission_group_id

            # Extract course_member_id from submission group members
            course_member_id = None
            if sg and sg.members:
                course_member_id = sg.members[0].course_member_id if sg.members else None

            await agent.process_message(
                submission_group_id=submission_group_id,
                message=message,
                course_content=course_content,  # Pass pre-fetched data
                course_member_id=course_member_id,
            )

        # Message trigger callback for WebSocket scheduler
        async def on_message_trigger_websocket(result, course_content, channel):
            """
            Handle message trigger from WebSocket scheduler.

            Args:
                result: TriggerCheckResult with message_trigger
                course_content: CourseContentStudentGet (may be None for WebSocket)
                channel: WebSocket channel (e.g., "submission_group:123")
            """
            logger.info(f"Processing message trigger (WebSocket): {result.reason}")
            if dry_run:
                logger.info(f"[DRY RUN] Would process message: {result.message_trigger.message_id}")
                return

            # Get the message data
            message = {
                "id": result.message_trigger.message_id,
                "content": result.message_trigger.content,
                "title": result.message_trigger.title,
                "author_id": result.message_trigger.author_id,
            }

            submission_group_id = result.message_trigger.submission_group_id

            # For WebSocket, we may need to fetch course_content if needed
            # For now, pass None - the agent can work without it
            await agent.process_message(
                submission_group_id=submission_group_id,
                message=message,
                course_content=course_content,
                course_member_id=None,
            )

        # Try WebSocket first, fall back to HTTP polling
        scheduler = None
        use_websocket = False

        try:
            from computor_agent.tutor.websocket import ComputorWebSocket, WebSocketScheduler

            # Get token for WebSocket auth
            # For API token auth: use the static token
            # For username/password auth: extract the access token from the logged-in client
            token = computor_config.backend.get_api_token()
            if not token:
                # Try to get access token from the authenticated client session
                token = await client._auth_provider.get_access_token()
                if token:
                    logger.info("Using session access token for WebSocket authentication")

            if token:
                ws = ComputorWebSocket(
                    base_url=computor_config.backend.url,
                    token=token,
                )

                # Create token provider for refreshing on reconnect
                async def _provide_fresh_token() -> str | None:
                    """Get a fresh token for WebSocket reconnection."""
                    # For API token auth, the token is static
                    api_token = computor_config.backend.get_api_token()
                    if api_token:
                        return api_token
                    # For username/password auth, refresh via the client
                    new_token = await client._auth_provider.refresh_token()
                    if new_token:
                        return new_token
                    # Refresh failed — try re-login
                    try:
                        await client.login(
                            username=computor_config.backend.username,
                            password=computor_config.backend.get_password(),
                        )
                        return await client._auth_provider.get_access_token()
                    except Exception as e:
                        logger.error(f"Re-login failed during token refresh: {e}")
                        return None

                scheduler = WebSocketScheduler(
                    client=client,
                    ws=ws,
                    trigger_config=tutor_config.triggers,
                    on_message_trigger=on_message_trigger_websocket,
                    cooldown_seconds=scheduler_config.cooldown_seconds,
                    max_concurrent_processing=scheduler_config.max_concurrent_processing,
                    token_provider=_provide_fresh_token,
                )
                use_websocket = True
                logger.info("Using WebSocket for real-time events")
            else:
                logger.info("No authentication token available for WebSocket")

        except ImportError as e:
            logger.warning(f"WebSocket support not available ({e}), using HTTP polling")
        except Exception as e:
            logger.warning(f"WebSocket initialization failed ({e}), falling back to HTTP polling")

        # Fall back to HTTP polling if WebSocket not available
        if not use_websocket:
            scheduler = TutorScheduler(
                client=client,
                config=scheduler_config,
                trigger_config=tutor_config.triggers,
                on_message_trigger=on_message_trigger_polling,
            )
            logger.info("Using HTTP polling for message detection")

        # Handle shutdown gracefully
        shutdown_event = asyncio.Event()

        def signal_handler():
            logger.info("Shutdown signal received")
            shutdown_event.set()

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, signal_handler)

        # Start scheduler in background task
        scheduler_task = asyncio.create_task(_run_scheduler_with_shutdown(scheduler, shutdown_event, use_websocket))

        # Wait for shutdown signal or scheduler completion
        done, pending = await asyncio.wait(
            [scheduler_task, asyncio.create_task(shutdown_event.wait())],
            return_when=asyncio.FIRST_COMPLETED,
        )

        # Cancel pending tasks
        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # Stop scheduler
        await scheduler.stop()
        logger.info("Tutor scheduler stopped")

    await tutor_llm.close()
    console.print("[green]Tutor agent stopped.[/green]")


async def _run_scheduler_with_shutdown(scheduler, shutdown_event, use_websocket: bool):
    """Run scheduler and handle WebSocket reconnection on failure."""
    logger = logging.getLogger(__name__)

    if use_websocket:
        # For WebSocket, start() blocks until stopped or reconnection fails
        # The scheduler handles reconnection internally, so we only need to
        # signal shutdown if it exits (either stopped or max reconnects reached)
        try:
            await scheduler.start()
            # Scheduler exited normally (either stopped or max reconnects reached)
            logger.info("WebSocket scheduler exited")
        except Exception as e:
            error_str = str(e)
            status_code = getattr(getattr(e, "response", None), "status_code", None)
            if status_code == 401 or "401" in error_str or "Unauthorized" in error_str:
                logger.error("Authentication failed. Please check your credentials and try again.")
                logger.error("Run 'computor-agent login' to re-authenticate.")
            else:
                logger.error(f"WebSocket scheduler error: {e}")
        finally:
            # Only signal shutdown if we're not already shutting down
            if not shutdown_event.is_set():
                logger.info("Signaling shutdown after scheduler exit")
                shutdown_event.set()
    else:
        # For HTTP polling, start() returns immediately, scheduler runs in background
        try:
            await scheduler.start()
            # Wait indefinitely (shutdown will come from signal)
            await asyncio.Event().wait()
        except Exception as e:
            error_str = str(e)
            status_code = getattr(getattr(e, "response", None), "status_code", None)
            if status_code == 401 or "401" in error_str or "Unauthorized" in error_str:
                logger.error("Authentication failed. Please check your credentials and try again.")
                logger.error("Run 'computor-agent login' to re-authenticate.")
            else:
                logger.error(f"HTTP scheduler error: {e}")
            # Exit the program
            shutdown_event.set()


if __name__ == "__main__":
    cli()
