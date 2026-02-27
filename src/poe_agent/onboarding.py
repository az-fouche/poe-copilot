import json
from pathlib import Path

from rich.console import Console
from rich.prompt import Prompt

SETTINGS_DIR = Path.home() / ".poechat"
SETTINGS_FILE = SETTINGS_DIR / "settings.usr"

MODES = {
    "1": ("softcore_trade", "Softcore Trade"),
    "2": ("hardcore_trade", "Hardcore Trade"),
    "3": ("ssf", "Solo Self-Found (SSF)"),
    "4": ("hc_ssf", "Hardcore SSF"),
}

EXPERIENCE = {
    "1": ("newbie", "New player — still learning the ropes"),
    "2": ("casual", "Casual — know the basics, played a few leagues"),
    "3": ("intermediate", "Intermediate — comfortable with endgame"),
    "4": ("veteran", "Veteran — deep knowledge, min-maxing"),
}


def load_settings() -> dict | None:
    if SETTINGS_FILE.exists():
        return json.loads(SETTINGS_FILE.read_text())
    return None


def save_settings(settings: dict):
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2))


def run_onboarding() -> dict:
    console = Console()

    console.print(
        "\n[bold cyan]Welcome to PoE Chat![/bold cyan] "
        "Let's set up your profile.\n"
    )

    # --- League ---
    console.print("[bold]1. What league are you playing?[/bold]")
    console.print("   [dim]Enter the league name (e.g. Keepers, Standard)[/dim]")
    league = Prompt.ask("   League", default="Standard")

    # --- Mode ---
    console.print("\n[bold]2. Game mode?[/bold]")
    for key, (_, label) in MODES.items():
        console.print(f"   [{key}] {label}")
    mode_key = Prompt.ask("   Choice", choices=list(MODES.keys()), default="1")
    mode_id, mode_label = MODES[mode_key]

    # --- Experience ---
    console.print("\n[bold]3. How experienced are you with PoE?[/bold]")
    for key, (_, label) in EXPERIENCE.items():
        console.print(f"   [{key}] {label}")
    exp_key = Prompt.ask("   Choice", choices=list(EXPERIENCE.keys()), default="3")
    exp_id, exp_label = EXPERIENCE[exp_key]

    settings = {
        "league": league.strip(),
        "mode": mode_id,
        "experience": exp_id,
    }

    save_settings(settings)

    console.print(f"\n[green]Profile saved to {SETTINGS_FILE}[/green]")
    console.print(
        f"   League: [bold]{settings['league']}[/bold] | "
        f"Mode: [bold]{mode_label}[/bold] | "
        f"Experience: [bold]{exp_label}[/bold]\n"
    )
    console.print("[dim]Run with --setup to change these later.[/dim]\n")

    return settings
