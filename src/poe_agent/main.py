import os
import sys

from dotenv import load_dotenv
from InquirerPy import inquirer
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.prompt import Prompt
from rich.spinner import Spinner

from .agent import ClarificationRequest, PoeAgent
from .onboarding import load_settings, run_onboarding


def _ask_clarifying_questions(
    console: Console,
    clarification: ClarificationRequest,
) -> str:
    """Render interactive menus for clarifying questions, return answers as text."""
    console.print()
    answers = []
    for q in clarification.questions:
        options = list(q.options)
        if not any(o.lower().startswith("other") for o in options):
            options.append("Other (type your answer)")

        choice = inquirer.select(
            message=q.question,
            choices=options,
        ).execute()

        if choice and choice.lower().startswith("other"):
            choice = Prompt.ask(f"  [dim]Your answer[/dim]")

        answers.append(f"{q.question} {choice}")

    return "; ".join(answers)


def main():
    load_dotenv()
    console = Console()

    force_setup = "--setup" in sys.argv

    settings = load_settings()
    if settings is None or force_setup:
        settings = run_onboarding()

    console.print(
        "\n[bold cyan]PoE Chat[/bold cyan] — your Path of Exile companion"
    )
    console.print(
        f"[dim]{settings['league']} · {settings['mode']} · {settings['experience']}[/dim]"
    )
    console.print(
        "Type [bold]/quit[/bold] to exit, "
        "[bold]/clear[/bold] to clear history, "
        "[bold]/setup[/bold] to reconfigure\n"
    )

    agent = PoeAgent(settings=settings)

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
            agent = PoeAgent(settings=settings)
            console.print("[dim]Agent reloaded with new settings.[/dim]\n")
            continue
        if not stripped:
            continue

        try:
            # First pass — may return clarification or answer
            spinner = Spinner("dots", text="Analyzing your question...")
            with Live(spinner, console=console, transient=True):
                def update_status(text: str):
                    spinner.update(text=text)

                result = agent.chat(user_input, on_status=update_status)

            # Handle clarification loop
            if isinstance(result, ClarificationRequest):
                answers_text = _ask_clarifying_questions(console, result)
                # Re-send original question with clarification answers
                enriched_input = f"{user_input}\n\n(My answers: {answers_text})"
                spinner = Spinner("dots", text="Researching...")
                with Live(spinner, console=console, transient=True):
                    def update_status_2(text: str):
                        spinner.update(text=text)

                    result = agent.chat(
                        enriched_input,
                        on_status=update_status_2,
                        skip_router=True,
                    )

            # At this point result should be a string
            if isinstance(result, str):
                console.print()
                console.print(Markdown(result))
                console.print()
            else:
                # Shouldn't happen, but handle gracefully
                console.print("\n[dim]Could not generate a response. Please try again.[/dim]\n")

        except Exception as e:
            console.print(f"\n[bold red]Error:[/bold red] {e}\n")


if __name__ == "__main__":
    main()
