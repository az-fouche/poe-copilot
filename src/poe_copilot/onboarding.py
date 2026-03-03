"""User onboarding flow and settings persistence."""

import json

from rich.console import Console
from rich.prompt import Prompt

from .constants import (
    SETTINGS_DIR,
    SETTINGS_FILE,
    Backend,
    Experience,
    GameMode,
    League,
)
from .backends.ollama import list_models
from .core.context import resolve_league

MODES = {
    "1": (GameMode.SOFTCORE_TRADE, "Softcore Trade"),
    "2": (GameMode.HARDCORE_TRADE, "Hardcore Trade"),
    "3": (GameMode.SSF, "Solo Self-Found (SSF)"),
    "4": (GameMode.HC_SSF, "Hardcore SSF"),
}

EXPERIENCE = {
    "1": (Experience.NEWBIE, "New player — still learning the ropes"),
    "2": (Experience.CASUAL, "Casual — know the basics, played a few leagues"),
    "3": (Experience.INTERMEDIATE, "Intermediate — comfortable with endgame"),
    "4": (Experience.VETERAN, "Veteran — deep knowledge, min-maxing"),
}


def load_settings() -> dict | None:
    """Load user settings from the configuration file.

    Returns
    -------
    dict or None
        Parsed settings dictionary, or ``None`` if the file does not exist.
    """
    if SETTINGS_FILE.exists():
        data: dict = json.loads(SETTINGS_FILE.read_text())
        return data
    return None


def save_settings(settings: dict) -> None:
    """Persist user settings to the configuration file.

    Parameters
    ----------
    settings : dict
        Settings dictionary to serialize as JSON.
    """
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2))


def needs_setup(settings: dict | None) -> bool:
    """Check whether onboarding is required."""
    if settings is None:
        return True
    backend = settings.get("backend", Backend.ANTHROPIC)
    if backend == Backend.OLLAMA:
        return not settings.get("ollama_model")
    return not settings.get("api_key")


def _ask_backend(console: Console, existing: dict | None) -> Backend:
    """Prompt for LLM backend choice."""
    prev = (existing or {}).get("backend", Backend.ANTHROPIC)
    default_backend = "1" if prev == Backend.ANTHROPIC else "2"
    console.print("[bold]1. LLM backend[/bold]")
    console.print("   [1] Anthropic (Claude API)")
    console.print("   [2] Ollama (local)")
    backend_key = Prompt.ask(
        "   Choice [1/2]",
        choices=["1", "2"],
        default=default_backend,
    )
    return Backend.ANTHROPIC if backend_key == "1" else Backend.OLLAMA


def _ask_anthropic_config(console: Console, existing: dict | None) -> str:
    """Prompt for Anthropic API key."""
    default_key = (existing or {}).get("api_key", "")
    if default_key:
        masked = default_key[:10] + "..." + default_key[-4:]
        console.print(
            f"\n[bold]2. Anthropic API key[/bold]"
            f"  [dim](current: {masked})[/dim]"
        )
        console.print("   [dim]Press Enter to keep, or paste a new one[/dim]")
        console.print("   [dim](input is hidden for security)[/dim]")
        new_key = Prompt.ask("   API key", default="***", password=True)
        return str(new_key) if new_key != "***" else default_key
    console.print("\n[bold]2. Anthropic API key[/bold]")
    console.print("   [dim]Get one at https://console.anthropic.com/[/dim]")
    console.print("   [dim](input is hidden for security)[/dim]")
    return str(Prompt.ask("   API key", password=True))


def _ask_ollama_config(
    console: Console, existing: dict | None
) -> tuple[str, str]:
    """Prompt for Ollama server URL and model name."""
    default_url = (existing or {}).get("ollama_url", "http://localhost:11434")
    console.print("\n[bold]2. Ollama server URL[/bold]")
    ollama_url = Prompt.ask("   URL", default=default_url)

    default_model = (existing or {}).get("ollama_model", "")
    models = list_models(ollama_url)

    if models:
        console.print("\n[bold]   Model[/bold]")
        for i, name in enumerate(models, 1):
            console.print(f"   [{i}] {name}")
        choices = [str(i) for i in range(1, len(models) + 1)]
        # Pre-select the previously chosen model if it's in the list
        default_choice = "1"
        if default_model in models:
            default_choice = str(models.index(default_model) + 1)
        pick = Prompt.ask(
            "   Choice",
            choices=choices,
            default=default_choice,
        )
        ollama_model = models[int(pick) - 1]
    else:
        console.print(
            f"\n[yellow]   Could not fetch models from {ollama_url}[/yellow]"
        )
        console.print("\n[bold]   Model name[/bold]")
        console.print("   [dim]e.g. qwen2.5:14b, llama3:8b[/dim]")
        ollama_model = Prompt.ask(
            "   Model",
            default=default_model or "qwen2.5:14b",
        )

    return ollama_url, ollama_model


def _ask_league(console: Console) -> League:
    """Prompt for league preference."""
    console.print("\n[bold]3. Do you play Standard or League?[/bold]")
    console.print("   [1] League (current challenge league)")
    console.print("   [2] Standard")
    league_key = Prompt.ask("   Choice [1/2]", choices=["1", "2"], default="1")
    return League.CHALLENGE if league_key == "1" else League.STANDARD


def _ask_mode(console: Console) -> tuple[str, str]:
    """Prompt for game mode."""
    console.print("\n[bold]4. Game mode?[/bold]")
    for key, (_, label) in MODES.items():
        console.print(f"   [{key}] {label}")
    mode_key = Prompt.ask("   Choice", choices=list(MODES.keys()), default="1")
    mode_id, mode_label = MODES[mode_key]
    return mode_id, mode_label


def _ask_experience(console: Console) -> tuple[str, str]:
    """Prompt for experience level."""
    console.print("\n[bold]5. How experienced are you with PoE?[/bold]")
    for key, (_, label) in EXPERIENCE.items():
        console.print(f"   [{key}] {label}")
    exp_key = Prompt.ask(
        "   Choice",
        choices=list(EXPERIENCE.keys()),
        default="3",
    )
    exp_id, exp_label = EXPERIENCE[exp_key]
    return exp_id, exp_label


def run_onboarding(existing: dict | None = None) -> dict:
    """Run the interactive onboarding wizard and save the resulting settings.

    Parameters
    ----------
    existing : dict or None, optional
        Previously saved settings used as defaults.

    Returns
    -------
    dict
        Completed settings dictionary (also persisted to disk).
    """
    console = Console()

    console.print(
        "\n[bold cyan]Welcome to PoE Chat![/bold cyan]"
        " Let's set up your profile.\n"
    )

    backend = _ask_backend(console, existing)

    settings: dict[str, str] = {"backend": backend}
    if backend == Backend.ANTHROPIC:
        settings["api_key"] = _ask_anthropic_config(console, existing).strip()
    else:
        url, model = _ask_ollama_config(console, existing)
        settings["ollama_url"] = url.strip()
        settings["ollama_model"] = model.strip()

    league = _ask_league(console)
    mode_id, mode_label = _ask_mode(console)
    exp_id, exp_label = _ask_experience(console)
    settings |= {
        "league": league.strip(),
        "mode": mode_id,
        "experience": exp_id,
    }

    save_settings(settings)

    resolved = resolve_league(settings)
    console.print(f"\n[green]Profile saved to {SETTINGS_FILE}[/green]")
    console.print(
        f"   League: [bold]{resolved}[/bold]"
        f" | Mode: [bold]{mode_label}[/bold]"
        f" | Experience: [bold]{exp_label}[/bold]\n"
    )
    console.print("[dim]Run with --setup to change these later.[/dim]\n")

    return settings
