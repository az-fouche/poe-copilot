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


def run_onboarding(existing: dict | None = None) -> dict:
    """Run the interactive onboarding wizard and save the resulting settings.

    Prompts the user for API key, league preference, game mode, and
    experience level via Rich console menus.

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

    # --- Backend ---
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
    backend = Backend.ANTHROPIC if backend_key == "1" else Backend.OLLAMA

    # --- Backend-specific config ---
    api_key = ""
    ollama_url = ""
    ollama_model = ""
    if backend == Backend.ANTHROPIC:
        default_key = (existing or {}).get("api_key", "")
        if default_key:
            masked = default_key[:10] + "..." + default_key[-4:]
            console.print(
                f"\n[bold]2. Anthropic API key[/bold]"
                f"  [dim](current: {masked})[/dim]"
            )
            console.print(
                "   [dim]Press Enter to keep, or paste a new one[/dim]"
            )
            console.print("   [dim](input is hidden for security)[/dim]")
            new_key = Prompt.ask("   API key", default="***", password=True)
            api_key = new_key if new_key != "***" else default_key
        else:
            console.print("\n[bold]2. Anthropic API key[/bold]")
            console.print(
                "   [dim]Get one at https://console.anthropic.com/[/dim]"
            )
            console.print("   [dim](input is hidden for security)[/dim]")
            api_key = Prompt.ask("   API key", password=True)
    else:
        default_url = (existing or {}).get(
            "ollama_url", "http://localhost:11434"
        )
        console.print("\n[bold]2. Ollama server URL[/bold]")
        ollama_url = Prompt.ask("   URL", default=default_url)
        default_model = (existing or {}).get("ollama_model", "")
        console.print("\n[bold]   Model name[/bold]")
        console.print("   [dim]e.g. qwen2.5:14b, llama3:8b[/dim]")
        ollama_model = Prompt.ask(
            "   Model",
            default=default_model or "qwen2.5:14b",
        )

    # --- League ---
    console.print("\n[bold]3. Do you play Standard or League?[/bold]")
    console.print("   [1] League (current challenge league)")
    console.print("   [2] Standard")
    league_key = Prompt.ask("   Choice [1/2]", choices=["1", "2"], default="1")
    league = League.CHALLENGE if league_key == "1" else League.STANDARD

    # --- Mode ---
    console.print("\n[bold]4. Game mode?[/bold]")
    for key, (_, label) in MODES.items():
        console.print(f"   [{key}] {label}")
    mode_key = Prompt.ask("   Choice", choices=list(MODES.keys()), default="1")
    mode_id, mode_label = MODES[mode_key]

    # --- Experience ---
    console.print("\n[bold]5. How experienced are you with PoE?[/bold]")
    for key, (_, label) in EXPERIENCE.items():
        console.print(f"   [{key}] {label}")
    exp_key = Prompt.ask(
        "   Choice",
        choices=list(EXPERIENCE.keys()),
        default="3",
    )
    exp_id, exp_label = EXPERIENCE[exp_key]

    settings: dict[str, str] = {
        "backend": backend,
        "league": league.strip(),
        "mode": mode_id,
        "experience": exp_id,
    }
    if backend == Backend.ANTHROPIC:
        settings["api_key"] = api_key.strip()
    else:
        settings["ollama_url"] = ollama_url.strip()
        settings["ollama_model"] = ollama_model.strip()

    save_settings(settings)

    resolved = resolve_league(settings)
    console.print(f"\n[green]Profile saved to {SETTINGS_FILE}[/green]")
    console.print(
        f"   League: [bold]{resolved}[/bold] | Mode: [bold]{mode_label}[/bold] | Experience: [bold]{exp_label}[/bold]\n"
    )
    console.print("[dim]Run with --setup to change these later.[/dim]\n")

    return settings
