"""Context and primer construction for agent system prompts."""

import re
from datetime import date

from poe_copilot.constants import (
    AGENTS_DIR,
    IDENTITY_FILE,
    LOADOUTS_DIR,
    PLAYER_CONTEXT_FILE,
    PRE_LAUNCH_DAYS,
    TIMELINE_FILE,
    Experience,
    GameMode,
    League,
)


def _load_timeline() -> str:
    """Read agents/timeline.md and return its contents, or empty string if missing."""
    if TIMELINE_FILE.exists():
        text = TIMELINE_FILE.read_text(encoding="utf-8").strip()
        if text:
            return text
    return ""


def _parse_timeline() -> list[tuple[date, str | None, str]]:
    """Parse timeline.md into (date, league_name, raw_line) tuples, sorted chronologically."""
    text = _load_timeline()
    if not text:
        return []

    entries: list[tuple[date, str | None, str]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        # Extract YYYY-MM-DD prefix
        m_date = re.match(r"(\d{4}-\d{2}-\d{2})", line)
        if not m_date:
            continue
        entry_date = date.fromisoformat(m_date.group(1))
        # Extract league name from pattern like "3.28 Mirage league"
        m_league = re.search(r"\d+\.\d+\s+(\w+)\s+league", line)
        league_name = m_league.group(1) if m_league else None
        entries.append((entry_date, league_name, line))

    entries.sort(key=lambda e: e[0])
    return entries


def _annotate_timeline(
    entries: list[tuple[date, str | None, str]], today: date
) -> tuple[str, str | None, tuple[str, str, date] | None]:
    """Annotate timeline entries with temporal markers and derive current/next league."""
    annotated_lines: list[str] = []
    current_league: str | None = None
    next_league: tuple[str, str, date] | None = None

    for entry_date, league_name, raw_line in entries:
        if entry_date <= today:
            annotated_lines.append(raw_line)
            if league_name:
                current_league = league_name
        else:
            # Rewrite past-tense "launched" to future-tense "launches"
            fixed = raw_line.replace(" launched.", " launches.").replace(
                " launched ", " launches "
            )
            annotated_lines.append(f"{fixed} \u26a0\ufe0f NOT YET LIVE")
            if league_name and next_league is None:
                # Extract version string like "3.28"
                m_ver = re.search(
                    r"(\d+\.\d+)\s+" + re.escape(league_name), raw_line
                )
                version = m_ver.group(1) if m_ver else ""
                next_league = (league_name, version, entry_date)

    return "\n\n".join(annotated_lines), current_league, next_league


def resolve_league(settings: dict) -> str:
    """Resolve the display league name from user settings.

    Maps the ``"league"`` setting to a display-ready name: ``"standard"``
    becomes ``"Standard"``, ``"challenge"`` is resolved to the current
    league name from ``timeline.md`` (falling back to ``"Standard"``).

    Parameters
    ----------
    settings : dict
        User settings containing a ``"league"`` key with value
        ``"standard"``, ``"challenge"``, or a literal league name.

    Returns
    -------
    str
        Display-ready league name (e.g. ``"Standard"`` or ``"Mirage"``).
    """
    raw = settings.get("league", League.STANDARD)
    if raw == League.STANDARD:
        return "Standard"
    if raw == League.CHALLENGE:
        entries = _parse_timeline()
        if entries:
            _, current_league, _ = _annotate_timeline(entries, date.today())
            if current_league:
                return current_league
        return "Standard"
    # Legacy: treat any other value as a literal league name
    return str(raw)


def _load_identity() -> str:
    """Read the agent identity text from assets."""
    return IDENTITY_FILE.read_text(encoding="utf-8").strip()


def _load_player_template() -> str:
    """Read the player context template from assets."""
    return PLAYER_CONTEXT_FILE.read_text(encoding="utf-8")


def _select_block(template: str, prefix: str, key: str) -> str:
    """Extract a named block from the template.

    Blocks are delimited by ``<!-- PREFIX:key -->`` markers.
    Returns text between the matching marker and the next marker
    (or end of file), stripped.
    """
    marker = f"<!-- {prefix}:{key} -->"
    start = template.find(marker)
    if start == -1:
        return ""
    start += len(marker)
    # Find next marker or end of text
    next_marker = template.find("<!-- ", start)
    if next_marker == -1:
        return template[start:].strip()
    return template[start:next_marker].strip()


def build_player_context(settings: dict) -> str:
    """Build the dynamic player-profile context appended to every agent primer.

    Assembles temporal grounding, game timeline, player profile, league
    rules, game mode, and communication style into a multi-section
    markdown string.

    Parameters
    ----------
    settings : dict
        User settings with ``"league"``, ``"mode"``, and ``"experience"`` keys.

    Returns
    -------
    str
        Multi-section markdown context string.
    """
    league = resolve_league(settings)
    mode = settings.get("mode", GameMode.SOFTCORE_TRADE)
    experience = settings.get("experience", Experience.INTERMEDIATE)

    today = date.today()
    today_str = today.strftime("%B %d, %Y").replace(" 0", " ")

    # Build timeline section
    entries = _parse_timeline()
    if entries:
        annotated_text, current_league, next_league = _annotate_timeline(
            entries, today
        )
        if current_league:
            league = current_league
        timeline_section = (
            "\n## Game Timeline "
            "(AUTHORITATIVE — overrides your training data)\n"
            "CRITICAL: The timeline below is the ground truth "
            "for what has happened in "
            "Path of Exile. Your training data about PoE league "
            "dates, names, and content "
            "is WRONG and outdated — do NOT use it. When "
            "answering ANY question about "
            "past, current, or upcoming leagues, rely ONLY on "
            "this timeline. If a league "
            "is not listed here, you do not know about it — "
            "say so and search instead.\n\n" + annotated_text
        )
    else:
        next_league = None
        timeline_section = ""

    # Pre-launch promotion: upcoming league becomes "the" league
    ninja_league = league
    pre_launch = False
    if next_league:
        days_until = (next_league[2] - today).days
        if 0 < days_until <= PRE_LAUNCH_DAYS:
            ninja_league = league
            league = next_league[0]
            pre_launch = True

    # Build next-league line
    if pre_launch:
        name, version, launch_date = next_league  # type: ignore[misc]
        friendly = launch_date.strftime("%B %d, %Y").replace(" 0", " ")
        next_league_line = f"- Launches {friendly} — NOT YET LIVE"
    elif next_league:
        name, version, launch_date = next_league
        friendly = launch_date.strftime("%B %d, %Y").replace(" 0", " ")
        next_league_line = (
            f"- Next league: **{name}** ({version}) "
            f"— launches {friendly}. NOT YET LIVE."
        )
    else:
        next_league_line = "- Next league: not yet announced — search for news."

    # Select blocks from template
    template = _load_player_template()
    mode_context = _select_block(template, "MODE", mode)
    exp_context = _select_block(template, "EXP", experience)
    pre_launch_note = (
        _select_block(template, "NOTE", "pre_launch") if pre_launch else ""
    )

    # The template body ends before the first marker
    marker_start = template.find("<!-- MODE:")
    body = template[:marker_start].rstrip() if marker_start != -1 else template

    return body.format(
        today=today_str,
        timeline_section=timeline_section,
        league=league,
        ninja_league=ninja_league,
        next_league_line=next_league_line,
        pre_launch_note=pre_launch_note,
        mode_context=mode_context,
        experience_context=exp_context,
    )


def load_loadout(name: str) -> str:
    """Load a loadout prompt fragment by name.

    Parameters
    ----------
    name : str
        Loadout name corresponding to a file in ``agents/loadouts/``.

    Returns
    -------
    str
        Loadout prompt text, or empty string if the file is missing.
    """
    path = LOADOUTS_DIR / f"{name}.md"
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def load_prompt(name: str) -> str:
    """Load an agent prompt template from disk.

    Parameters
    ----------
    name : str
        Agent name corresponding to a markdown file in ``agents/``.

    Returns
    -------
    str
        Raw prompt text from ``agents/{name}.md``.

    Raises
    ------
    FileNotFoundError
        If the prompt file does not exist.
    """
    path = AGENTS_DIR / f"{name}.md"
    return path.read_text(encoding="utf-8")


def build_primer(agent_name: str, settings: dict) -> str:
    """Compose the full system primer for an agent.

    Concatenates the global identity, the agent-specific prompt template,
    and the dynamic player context.

    Parameters
    ----------
    agent_name : str
        Agent name used to look up the prompt template.
    settings : dict
        User settings forwarded to `build_player_context`.

    Returns
    -------
    str
        Complete system prompt ready for the API.
    """
    return "\n\n".join(
        [
            _load_identity(),
            load_prompt(agent_name),
            build_player_context(settings),
        ]
    )
