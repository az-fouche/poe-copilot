import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from InquirerPy import inquirer
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.prompt import Prompt
from rich.spinner import Spinner

from .orchestrator import ClarificationRequest, Orchestrator
from .onboarding import load_settings, run_onboarding

logger = logging.getLogger(__name__)


def setup_logging():
    """Configure per-conversation file logging."""
    logs_dir = Path(__file__).resolve().parent.parent.parent / "logs"
    logs_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_file = logs_dir / f"{timestamp}.log"

    handler = logging.FileHandler(log_file, encoding="utf-8")
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s")
    )

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(handler)

    logger.info("Session started — log file: %s", log_file)


class TimedSpinner:
    """Spinner that shows elapsed time alongside status text."""

    def __init__(self, text="Working..."):
        self._spinner = Spinner("dots")
        self._text = text
        self._start = time.monotonic()

    def update(self, text):
        self._text = text

    def __rich_console__(self, console, options):
        elapsed = int(time.monotonic() - self._start)
        if elapsed >= 60:
            time_str = f"{elapsed // 60}m {elapsed % 60:02d}s"
        else:
            time_str = f"{elapsed}s"
        self._spinner.update(text=f"{self._text}  [dim]{time_str}[/dim]")
        yield from self._spinner.__rich_console__(console, options)


def _ask_clarifying_questions(
    console: Console,
    clarification: ClarificationRequest,
) -> str:
    """Render interactive menus for clarifying questions, return answers as text."""
    answers = []
    for q in clarification.questions:
        options = list(q.options)
        if not any(o.lower().startswith("other") for o in options):
            options.append("Other (type your answer)")

        choice = inquirer.select(  # type: ignore
            message=q.question,
            choices=options,
        ).execute()

        if choice and choice.lower().startswith("other"):
            choice = Prompt.ask("  [dim]Your answer[/dim]")

        answers.append(f"{q.question} {choice}")

    return "; ".join(answers)


def main():
    load_dotenv()
    setup_logging()
    console = Console(width=80)

    force_setup = "--setup" in sys.argv

    settings = load_settings()
    if settings is None or force_setup:
        settings = run_onboarding()

    logger.info("Settings: %s", settings)
    console.print("\n[bold cyan]PoE Chat[/bold cyan] — your Path of Exile companion")
    console.print(
        f"[dim]{settings['league']} · {settings['mode']} · {settings['experience']}[/dim]"
    )
    console.print(
        "Type [bold]/quit[/bold] to exit, "
        "[bold]/clear[/bold] to clear history, "
        "[bold]/setup[/bold] to reconfigure\n"
    )

    agent = Orchestrator(settings=settings)

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
            agent.messages.clear()
            os.system("cls" if os.name == "nt" else "clear")
            console.print("[dim]Conversation cleared.[/dim]\n")
            continue
        if stripped == "/setup":
            settings = run_onboarding()
            agent = Orchestrator(settings=settings)
            console.print("[dim]Agent reloaded with new settings.[/dim]\n")
            continue
        if not stripped:
            continue

        console.print()

        try:
            def show_message(text: str):
                console.print(f"\n[dim]{text}[/dim]\n")

            # First pass — may return clarification or answer
            spinner = TimedSpinner("Analyzing your question...")
            with Live(spinner, console=console, transient=True):

                def update_status(text: str):
                    spinner.update(text)

                result = agent.run(
                    user_input,
                    on_status=update_status,
                    on_message=show_message,
                )

            # Handle clarification loop (max 2 rounds)
            max_clarification_rounds = 2
            clarification_round = 0
            while isinstance(result, ClarificationRequest) and clarification_round < max_clarification_rounds:
                clarification_round += 1
                answers_text = _ask_clarifying_questions(console, result)
                enriched_input = f"{user_input}\n\n(My answers: {answers_text})"
                spinner = TimedSpinner("Researching...")
                with Live(spinner, console=console, transient=True):

                    def _make_status_cb(s):
                        return lambda text: s.update(text)

                    result = agent.run(
                        enriched_input,
                        on_status=_make_status_cb(spinner),
                        on_message=show_message,
                        start_agent="router",
                        clarification_round=clarification_round,
                    )

            # At this point result should be a string
            if isinstance(result, str):
                console.print()
                console.print(Markdown(result))
                console.print()
            else:
                # Shouldn't happen, but handle gracefully
                console.print(
                    "\n[dim]Could not generate a response. Please try again.[/dim]\n"
                )

        except Exception as e:
            console.print(f"\n[bold red]Error:[/bold red] {e}\n")


if __name__ == "__main__":
    main()
