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
    # Reduce noise from httpx
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


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
    type=float,
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


@cli.command()
@click.option(
    "--config",
    "-c",
    type=click.Path(exists=True),
    default="config.yaml",
    help="Path to config file (default: config.yaml)",
)
@click.option(
    "--credentials",
    type=click.Path(exists=True),
    default="credentials.yaml",
    help="Path to Git credentials file (default: credentials.yaml)",
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
def tutor(
    config: str,
    credentials: str,
    verbose: bool,
    dry_run: bool,
):
    """
    Start the Tutor AI agent.

    The tutor agent polls for student messages and submissions,
    and responds automatically using the configured LLM.

    Examples:

        # Start with config files in current directory
        computor-agent tutor

        # Use specific config files
        computor-agent tutor -c ~/.computor/config.yaml

        # Verbose mode
        computor-agent tutor -v
    """
    setup_logging(verbose)
    logger = logging.getLogger(__name__)

    # Load configuration
    config_path = Path(config)
    credentials_path = Path(credentials)

    try:
        from computor_agent.settings import ComputorConfig, GitCredentialsStore
        from computor_agent.tutor import TutorConfig

        logger.info(f"Loading config from {config_path}")
        computor_config = ComputorConfig.from_file(config_path)

        logger.info(f"Loading credentials from {credentials_path}")
        git_credentials = GitCredentialsStore.from_file(credentials_path)

        # Load tutor config if exists
        tutor_config_path = config_path.parent / "tutor.yaml"
        if tutor_config_path.exists():
            logger.info(f"Loading tutor config from {tutor_config_path}")
            tutor_config = TutorConfig.from_file(tutor_config_path)
        else:
            logger.info("Using default tutor config")
            tutor_config = TutorConfig()

    except FileNotFoundError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        sys.exit(1)
    except Exception as e:
        console.print(f"[bold red]Configuration error:[/bold red] {e}")
        sys.exit(1)

    # Show configuration summary
    console.print(
        Panel(
            f"[bold cyan]Tutor AI Agent[/bold cyan]\n\n"
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

    asyncio.run(_run_tutor(computor_config, tutor_config, git_credentials, dry_run))


async def _run_tutor(computor_config, tutor_config, git_credentials, dry_run: bool):
    """Run the tutor agent."""
    from computor_client import ComputorClient

    from computor_agent.llm.config import LLMConfig, ProviderType
    from computor_agent.llm.factory import get_provider
    from computor_agent.tutor import TutorAgent, TutorScheduler, SchedulerConfig, TutorClientAdapter, TutorLLMAdapter

    logger = logging.getLogger(__name__)

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

        # Wrap client with adapter for TutorAgent compatibility
        tutor_client = TutorClientAdapter(client)

        # Create tutor agent
        agent = TutorAgent(
            config=tutor_config,
            llm=tutor_llm,
            client=tutor_client,
        )

        # Create scheduler
        scheduler_config = SchedulerConfig(
            enabled=True,
            poll_interval_seconds=tutor_config.scheduler.poll_interval_seconds
            if hasattr(tutor_config, "scheduler") and tutor_config.scheduler
            else 30,
        )

        async def on_message_trigger(result, submission_group):
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
            await agent.process_message(
                submission_group_id=result.message_trigger.submission_group_id,
                message=message,
            )

        async def on_submission_trigger(result, submission_group):
            logger.info(f"Processing submission trigger")
            if dry_run:
                logger.info(f"[DRY RUN] Would process submission: {result.submission_trigger.artifact_id}")
                return

            # Build artifact dict
            artifact = {
                "id": result.submission_trigger.artifact_id,
            }
            await agent.process_submission(
                submission_group_id=result.submission_trigger.submission_group_id,
                artifact=artifact,
            )

        scheduler = TutorScheduler(
            client=client,
            config=scheduler_config,
            trigger_config=tutor_config.triggers,
            on_message_trigger=on_message_trigger,
            on_submission_trigger=on_submission_trigger,
        )

        # Handle shutdown gracefully
        shutdown_event = asyncio.Event()

        def signal_handler():
            logger.info("Shutdown signal received")
            shutdown_event.set()

        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, signal_handler)

        # Start scheduler
        await scheduler.start()
        logger.info("Tutor scheduler started")

        # Wait for shutdown
        await shutdown_event.wait()

        # Stop scheduler
        await scheduler.stop()
        logger.info("Tutor scheduler stopped")

    await tutor_llm.close()
    console.print("[green]Tutor agent stopped.[/green]")


if __name__ == "__main__":
    cli()
