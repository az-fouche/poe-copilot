"""Centralized CLI utilities — spinners, logging, prompts, and status labels."""

import logging
import os
import time
from collections.abc import Generator
from datetime import datetime
from typing import Any, Callable

from InquirerPy import inquirer
from rich.console import Console, ConsoleOptions
from rich.live import Live
from rich.prompt import Prompt
from rich.spinner import Spinner

from poe_copilot.config import (
    SECONDS_PER_MINUTE,
    TRUNCATE_ITEM_TYPE_CHARS,
    TRUNCATE_LONG_URL_CHARS,
    TRUNCATE_NAME_FILTER_CHARS,
    TRUNCATE_QUERY_CHARS,
    TRUNCATE_SECTION_CHARS,
    TRUNCATE_SHORT_URL_CHARS,
)
from poe_copilot.constants import LOGS_DIR, SPINNER_LABELS_FILE
from poe_copilot.core.agent import ClarifyingQuestion

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────

POE_SPINNER_LABELS: list[str] = [
    f"{w}..."
    for line in SPINNER_LABELS_FILE.read_text().splitlines()
    if (w := line.strip())
]

# Friendly spinner labels for agents and delegation tools
STATUS_LABELS: dict[str, str] = {
    "router": "Analyzing your question...",
    "analyst": "Researching...",
    "fact_checker": "Checking research quality...",
    "answerer": "Writing response...",
}

# ── Helper functions ──────────────────────────────────────────────────────


def truncate(text: str, max_len: int) -> str:
    """Truncate text to a maximum length, adding an ellipsis if truncated."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "\u2026"


def tool_status_label(name: str, tool_input: dict) -> str:
    """Build a dynamic spinner label based on tool name and its inputs."""
    if name == "read_webpage":
        url = tool_input.get("url", "")
        section = tool_input.get("section", "")
        short_url = url.replace("https://", "").replace("http://", "")
        if section:
            return f'Reading "{truncate(section, TRUNCATE_SECTION_CHARS)}" from {truncate(short_url, TRUNCATE_SHORT_URL_CHARS)}'
        return f"Reading {truncate(short_url, TRUNCATE_LONG_URL_CHARS)}"

    if name == "poe_web_search":
        query = tool_input.get("query", "")
        if query:
            return f"Searching: {truncate(query, TRUNCATE_QUERY_CHARS)}"
        return "Searching the web..."

    if name == "get_item_prices":
        name_filter = tool_input.get("name", "")
        item_type = tool_input.get("type", "")
        if name_filter:
            return f'Looking up "{truncate(name_filter, TRUNCATE_NAME_FILTER_CHARS)}" prices...'
        if item_type:
            return f"Looking up {truncate(item_type, TRUNCATE_ITEM_TYPE_CHARS)} prices..."
        return "Looking up item prices..."

    if name == "get_build_meta":
        class_filter = tool_input.get("class_filter", "")
        league = tool_input.get("league", "")
        if class_filter and league:
            return f"Checking {class_filter} builds ({league})"
        if class_filter:
            return f"Checking {class_filter} builds"
        if league:
            return f"Checking build meta ({league})"
        return "Checking build meta"

    if name == "get_currency_prices":
        return "Checking currency prices..."

    if name == "query_game_data":
        queries = tool_input.get("queries", [])
        if queries:
            return f"Querying game data: {truncate(', '.join(queries), 40)}"
        return "Querying game data..."

    return f"Using {name}..."


def check_esc() -> bool:
    """Non-blocking ESC key detection (Windows only, no-op elsewhere)."""
    if os.name != "nt":
        return False
    import msvcrt

    if msvcrt.kbhit() and msvcrt.getch() == b"\x1b":  # type: ignore[attr-defined]
        return True
    return False


# ── TimedSpinner ──────────────────────────────────────────────────────────


class TimedSpinner:
    """Rich-renderable spinner that shows elapsed time alongside status text.

    Used by the CLI to give the user feedback while agents are processing.

    Parameters
    ----------
    text : str, optional
        Initial status message displayed next to the spinner
        (default ``"Working..."``).
    """

    def __init__(self, text: str = "Working...") -> None:
        """Initialize the spinner with the given status text."""
        self._spinner = Spinner("dots")
        self._text = text
        self._start = time.monotonic()

    def update(self, text: str) -> None:
        """Replace the current status message.

        Parameters
        ----------
        text : str
            New status message to display alongside the elapsed time.
        """
        self._text = text

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> Generator[Any, None, None]:
        """Yield renderables for the Rich Live display.

        Parameters
        ----------
        console : rich.console.Console
            The active console instance.
        options : rich.console.ConsoleOptions
            Current rendering options.

        Yields
        ------
        RenderableType
            Spinner renderables with elapsed-time annotation.
        """
        elapsed = int(time.monotonic() - self._start)
        if elapsed >= SECONDS_PER_MINUTE:
            time_str = f"{elapsed // SECONDS_PER_MINUTE}m {elapsed % SECONDS_PER_MINUTE:02d}s"
        else:
            time_str = f"{elapsed}s"
        self._spinner.update(text=f"{self._text}  [dim]{time_str}[/dim]")
        yield from self._spinner.__rich_console__(console, options)


# ── Logging ───────────────────────────────────────────────────────────────


def setup_logging() -> None:
    """Configure file-based logging for the current conversation session.

    Creates a timestamped log file under the ``logs/`` directory at the
    project root and attaches a ``DEBUG``-level file handler to the root
    logger.
    """
    LOGS_DIR.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_file = LOGS_DIR / f"{timestamp}.log"

    handler = logging.FileHandler(log_file, encoding="utf-8")
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s")
    )

    root = logging.getLogger()
    root.setLevel(logging.WARNING)
    root.addHandler(handler)

    # Our package logs at DEBUG; third-party stays at WARNING
    logging.getLogger("poe_copilot").setLevel(logging.DEBUG)

    # Reduce noise from common third-party libraries
    for noisy in [
        "urllib3",
        "httpx",
        "openai",
        "anthropic",
        "rich",
        "InquirerPy",
    ]:
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logger.info("Session started — log file: %s", log_file)


# ── Interactive prompts ───────────────────────────────────────────────────


def ask_clarifying_questions(
    console: Console,
    clarification: list[ClarifyingQuestion],
) -> str:
    """Render interactive menus for clarifying questions, return answers as text."""
    answers = []
    for q in clarification:
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


def handle_interrupt(
    console: Console,
    steps_completed: int,
    force_answer_fn: Callable[[str], str],
) -> str | None:
    """Handle Ctrl+C during agent.run() — offer menu to salvage partial results."""
    console.print(
        f"\n[bold yellow]Interrupted[/bold yellow] — {steps_completed} step(s) completed so far."
    )

    try:
        choice = inquirer.select(  # type: ignore
            message="What would you like to do?",
            choices=[
                "Add more context and get answer",
                "Get answer with current data",
                "Cancel",
            ],
        ).execute()
    except KeyboardInterrupt:
        return None

    if choice == "Cancel":
        return None

    extra_context = ""
    if choice == "Add more context and get answer":
        try:
            extra_context = Prompt.ask("[dim]Additional context[/dim]")
        except KeyboardInterrupt:
            return None

    try:
        spinner = TimedSpinner("Writing response...")
        with Live(spinner, console=console, transient=True):
            return force_answer_fn(extra_context)
    except KeyboardInterrupt:
        return None
