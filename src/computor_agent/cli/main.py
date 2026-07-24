"""
MVP CLI for computor-agent.

A simple interactive CLI for testing LLM providers, similar to codex-cli.
Supports both complete and streaming modes.
"""

import asyncio
import logging
import os
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

from computor_agent.llm.config import LLMConfig, ProviderType
from computor_agent.llm.exceptions import LLMError
from computor_agent.llm.factory import get_provider, list_providers

# Load environment variables
load_dotenv()

console = Console()


def setup_logging(verbose: bool = False, log_file: Optional[str] = None) -> None:
    """Setup rich logging with optional file output."""
    level = logging.DEBUG if verbose else logging.INFO

    handlers: list[logging.Handler] = [
        RichHandler(console=console, rich_tracebacks=True),
    ]

    if log_file:
        from logging.handlers import RotatingFileHandler

        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        file_handler.setLevel(level)
        handlers.append(file_handler)

    # In-memory ring buffer feeds the dashboard so the UI never tails the
    # log file from disk — keeps the two views in lockstep even without
    # `--log-file`.
    from computor_agent.api.log_buffer import get_log_buffer

    buffer = get_log_buffer()
    buffer.setLevel(level)
    handlers.append(buffer)

    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=handlers,
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
@click.option(
    "--scenario",
    type=click.Path(exists=True),
    default=None,
    help="[Dev mode] Path to scenario directory (must contain scenario.yaml).",
)
@click.option(
    "--log-file",
    "-l",
    type=click.Path(),
    default=None,
    help="Log output to file (rotating, 10MB max, 3 backups).",
)
@click.option(
    "--prompt",
    "-p",
    type=str,
    default=None,
    help="[Dev mode] Process a single message and exit (no interactive loop).",
)
@click.option(
    "--api-port",
    type=int,
    default=None,
    help="Enable HTTP dashboard on this port (e.g. 8080). Off by default.",
)
@click.option(
    "--api-host",
    type=str,
    default="127.0.0.1",
    show_default=True,
    help="Bind address for the dashboard. Use 0.0.0.0 to expose externally.",
)
@click.option(
    "--llm-probe-interval",
    type=float,
    default=30.0,
    show_default=True,
    help="Seconds between LLM liveness probes. Set 0 to disable.",
)
@click.option(
    "--workers",
    "-w",
    type=click.IntRange(1, 50),
    default=None,
    help=(
        "Worker count: how many messages are processed concurrently. "
        "Overrides COMPUTOR_WORKERS and the config file."
    ),
)
def messaging(
    config: Optional[str],
    verbose: bool,
    dry_run: bool,
    dev: bool,
    prompts_dir: Optional[str],
    assignment: Optional[str],
    scenario: Optional[str],
    log_file: Optional[str],
    prompt: Optional[str],
    api_port: Optional[int],
    api_host: str,
    llm_probe_interval: float,
    workers: Optional[int],
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

        # With file logging
        computor-agent tutor messaging -v -l tutor.log
    """
    setup_logging(verbose, log_file=log_file)
    logger = logging.getLogger(__name__)

    if log_file:
        logger.info(f"Logging to file: {log_file}")

    # Resolve config path: try explicit, then config.yaml, then example.yaml
    if config is not None:
        config_path = Path(config)
        if not config_path.exists():
            logger.error(f"Config file '{config}' does not exist")
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
            logger.error("No config file found in current directory")
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
        scenario_path = Path(scenario) if scenario else None
        asyncio.run(run_development_mode(
            config_path,
            verbose,
            prompts_path,
            assignment_path=assignment_path,
            scenario_path=scenario_path,
            prompt=prompt,
        ))
        return

    try:
        from computor_agent.settings import ComputorConfig, apply_env_overrides

        logger.info(f"Loading config from {config_path}")
        computor_config = ComputorConfig.from_file(config_path)

        # COMPUTOR_* environment variables win over the config file...
        computor_config = apply_env_overrides(computor_config)
        # ...and an explicit --workers flag wins over both.
        if workers is not None:
            computor_config = apply_env_overrides(
                computor_config, {"COMPUTOR_WORKERS": str(workers)}
            )

        # Validate the tutor section here so config errors surface as a clean
        # message instead of a traceback from inside the runtime.
        computor_config.get_tutor_config()

    except FileNotFoundError as e:
        logger.error(f"Config file not found: {e}", exc_info=True)
        console.print(f"[bold red]Error:[/bold red] {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Configuration error: {e}", exc_info=True)
        console.print(f"[bold red]Configuration error:[/bold red] {e}")
        sys.exit(1)

    console.print(
        Panel(
            f"[bold cyan]Tutor AI Agent - Messaging[/bold cyan]\n\n"
            f"Backend: [green]{computor_config.backend.url}[/green]\n"
            f"Auth: [green]{computor_config.backend.auth_method}[/green]\n"
            f"LLM: [green]{computor_config.llm.provider if computor_config.llm else 'not configured'}[/green] "
            f"([green]{computor_config.llm.model if computor_config.llm else 'n/a'}[/green])\n"
            f"Dry run: [yellow]{dry_run}[/yellow]\n\n"
            f"Press [yellow]Ctrl+C[/yellow] to stop.",
            title="Starting",
        )
    )

    from computor_agent.runtime import AgentRuntime, RuntimeOptions

    options = RuntimeOptions(
        dry_run=dry_run,
        prompts_dir=Path(prompts_dir) if prompts_dir else None,
        api_port=api_port,
        api_host=api_host,
        log_file=log_file,
        llm_probe_interval=llm_probe_interval,
    )
    exit_code = asyncio.run(AgentRuntime(computor_config, options, console=console).run())
    if exit_code:
        sys.exit(exit_code)


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

    # Production mode - not yet implemented
    console.print("[yellow]Production grading mode is not yet implemented.[/yellow]")
    console.print("Use --dev mode for local testing:")
    console.print("  computor-agent tutor grading --dev --reference ./assignment --student ./submission")
    sys.exit(2)


if __name__ == "__main__":
    cli()
