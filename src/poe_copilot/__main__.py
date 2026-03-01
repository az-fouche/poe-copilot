"""CLI entry point for the PoE Chat interactive assistant."""

import logging
import os
import sys
import tomllib
from pathlib import Path
from typing import Callable

import anthropic
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.prompt import Prompt

from .backends.anthropic import AnthropicBackend
from .backends.backend import LLMBackend
from .backends.ollama import OllamaBackend
from .constants import Backend
from .core import Orchestrator, resolve_league
from .core.agent import ClarifyingQuestion
from .core.cli import (
    TimedSpinner,
    ask_clarifying_questions,
    handle_interrupt,
    setup_logging,
)
from .onboarding import load_settings, needs_setup, run_onboarding

logger = logging.getLogger(__name__)


def get_version() -> str:
    """Read version from pyproject.toml."""
    try:
        pyproject_path = (
            Path(__file__).resolve().parent.parent.parent / "pyproject.toml"
        )
        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)
            version: str = data.get("project", {}).get("version", "unknown")
            return version
    except Exception:
        return "unknown"


def _build_backend(settings: dict) -> LLMBackend:
    """Create the LLM backend from user settings."""
    if settings.get("backend") == Backend.OLLAMA:
        return OllamaBackend(
            base_url=settings["ollama_url"],
            model_override=settings["ollama_model"],
        )
    return AnthropicBackend(anthropic.Anthropic(api_key=settings["api_key"]))


def main() -> None:
    """Run the interactive PoE Chat REPL.

    Handles onboarding, settings loading, and the main input loop
    including clarification rounds and interrupt recovery.
    """
    console = Console(width=80)
    if "--version" in sys.argv or "-v" in sys.argv:
        console.print(get_version())
        sys.exit(0)

    setup_logging()

    force_setup = "--setup" in sys.argv

    settings = load_settings()
    if needs_setup(settings) or force_setup:
        settings = run_onboarding(existing=settings)
    if settings is None:
        raise RuntimeError("Failed to load settings after onboarding")

    logger.info("Settings: %s", settings)
    league_display = resolve_league(settings)
    console.print(
        "\n[bold cyan]PoE Chat[/bold cyan] — your Path of Exile companion"
    )
    console.print(
        f"[dim]{league_display} · {settings['mode']} · {settings['experience']}[/dim]"
    )
    console.print(
        "Type [bold]/quit[/bold] to exit, [bold]/clear[/bold] to clear history, [bold]/setup[/bold] to reconfigure"
    )
    console.print("Press [bold]Ctrl+C[/bold] to interrupt and take control\n")

    orchestrator = Orchestrator(
        settings=settings,
        backend=_build_backend(settings),
    )

    while True:
        try:
            user_input = Prompt.ask("[bold yellow]You[/bold yellow]")
        except (KeyboardInterrupt, EOFError):
            console.print("\nBye, exile.")
            break

        stripped = user_input.strip().lower()
        if stripped in ("/quit", "/exit", "quit", "exit"):
            console.print("Bye, exile.")
            break
        if stripped == "/clear":
            orchestrator.messages.clear()
            os.system("cls" if os.name == "nt" else "clear")
            console.print("[dim]Conversation cleared.[/dim]\n")
            continue
        if stripped == "/setup":
            settings = run_onboarding(existing=settings)
            orchestrator = Orchestrator(
                settings=settings,
                backend=_build_backend(settings),
            )
            console.print("[dim]Agent reloaded with new settings.[/dim]\n")
            continue
        if not stripped:
            continue

        console.print()

        try:

            def show_message(text: str) -> None:
                console.print(f"\n[dim]{text}[/dim]\n")

            # First pass — may return clarification or answer
            spinner = TimedSpinner("Analyzing your question...")
            try:
                with Live(spinner, console=console, transient=True):

                    def update_status(text: str) -> None:
                        spinner.update(text)

                    result: str | list[ClarifyingQuestion] | None = (
                        orchestrator.run(
                            user_input,
                            on_status=update_status,
                            on_message=show_message,
                        )
                    )
            except KeyboardInterrupt:
                result = handle_interrupt(
                    console,
                    max(0, orchestrator.api_calls - 1),
                    orchestrator.force_answer,
                )
                if result is None:
                    if (
                        orchestrator.messages
                        and orchestrator.messages[-1].get("role") == "user"
                    ):
                        orchestrator.messages.pop()
                    console.print("[dim]Cancelled.[/dim]\n")
                    continue

            # Handle clarification loop (max 2 rounds)
            max_clarification_rounds = 2
            clarification_round = 0
            while (
                isinstance(result, list)
                and clarification_round < max_clarification_rounds
            ):
                clarification_round += 1
                answers_text = ask_clarifying_questions(console, result)
                enriched_input = f"{user_input}\n\n(My answers: {answers_text})"
                spinner = TimedSpinner("Researching...")
                try:
                    with Live(spinner, console=console, transient=True):

                        def _make_status_cb(
                            s: TimedSpinner,
                        ) -> Callable[[str], None]:
                            return lambda text: s.update(text)

                        result = orchestrator.run(
                            enriched_input,
                            on_status=_make_status_cb(spinner),
                            on_message=show_message,
                            start_agent="router",
                            clarification_round=clarification_round,
                        )
                except KeyboardInterrupt:
                    result = handle_interrupt(
                        console,
                        orchestrator.api_calls,
                        orchestrator.force_answer,
                    )
                    if result is None:
                        if (
                            orchestrator.messages
                            and orchestrator.messages[-1].get("role") == "user"
                        ):
                            orchestrator.messages.pop()
                        console.print("[dim]Cancelled.[/dim]\n")
                        break

            # At this point result should be a string
            if isinstance(result, str):
                console.print()
                console.print(Markdown(result))
                console.print()
            elif result is not None:
                # Shouldn't happen, but handle gracefully
                console.print(
                    "\n[dim]Could not generate a response. Please try again.[/dim]\n"
                )

        except Exception as e:
            console.print(f"\n[bold red]Error:[/bold red] {e}\n")


if __name__ == "__main__":
    main()
