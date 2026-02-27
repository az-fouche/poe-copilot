import sys

from dotenv import load_dotenv
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.prompt import Prompt
from rich.spinner import Spinner

from .agent import PoeAgent
from .onboarding import load_settings, run_onboarding


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
        "[bold]/reset[/bold] to clear history, "
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
        if stripped == "/reset":
            agent.messages.clear()
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
            with Live(
                Spinner("dots", text="Thinking..."),
                console=console,
                transient=True,
            ):
                response = agent.chat(user_input)

            console.print()
            console.print(Markdown(response))
            console.print()
        except Exception as e:
            console.print(f"\n[bold red]Error:[/bold red] {e}\n")


if __name__ == "__main__":
    main()
