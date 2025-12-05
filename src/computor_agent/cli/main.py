"""
MVP CLI for computor-agent.

A simple interactive CLI for testing LLM providers, similar to codex-cli.
Supports both complete and streaming modes.
"""

import asyncio
import os
import sys
from typing import Optional

import click
from dotenv import load_dotenv
from rich.console import Console
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


if __name__ == "__main__":
    cli()
