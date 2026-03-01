from __future__ import annotations

import re
from datetime import date
from pathlib import Path

_AGENTS_DIR = Path(__file__).resolve().parent / "agents"
_TIMELINE_FILE = _AGENTS_DIR / "timeline.md"


def _load_timeline() -> str:
    """Read agents/timeline.md and return its contents, or empty string if missing."""
    if _TIMELINE_FILE.exists():
        text = _TIMELINE_FILE.read_text(encoding="utf-8").strip()
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
    """Annotate timeline entries and derive current/next league.

    Returns (annotated_text, current_league_name, next_league_info).
    next_league_info is (name, version, date) or None.
    """
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
            fixed = raw_line.replace(" launched.", " launches.").replace(" launched ", " launches ")
            annotated_lines.append(f"{fixed} \u26a0\ufe0f NOT YET LIVE")
            if league_name and next_league is None:
                # Extract version string like "3.28"
                m_ver = re.search(r"(\d+\.\d+)\s+" + re.escape(league_name), raw_line)
                version = m_ver.group(1) if m_ver else ""
                next_league = (league_name, version, entry_date)

    return "\n\n".join(annotated_lines), current_league, next_league


def resolve_league(settings: dict) -> str:
    """Resolve the display league name from settings.

    - "standard" → "Standard"
    - "challenge" → current league name from timeline.md, fallback "Standard"
    """
    raw = settings.get("league", "standard")
    if raw == "standard":
        return "Standard"
    if raw == "challenge":
        entries = _parse_timeline()
        if entries:
            _, current_league, _ = _annotate_timeline(entries, date.today())
            if current_league:
                return current_league
        return "Standard"
    # Legacy: treat any other value as a literal league name
    return raw


IDENTITY = (
    "You are a knowledgeable Path of Exile (PoE 1) companion. You help players "
    "with builds, game mechanics, economy, and strategy."
)

MODE_CONTEXT = {
    "softcore_trade": (
        "The player is in softcore trade league. Deaths are not permanent. "
        "They can trade freely, so gear recommendations can include trade purchases."
    ),
    "hardcore_trade": (
        "The player is in HARDCORE trade league. Death is permanent (character moves "
        "to Standard). ALWAYS prioritize survivability and defensive layers. Avoid "
        "recommending glass cannon builds. EHP and max hit taken matter enormously."
    ),
    "ssf": (
        "The player is in SSF (Solo Self-Found). They CANNOT trade with other players. "
        "All gear must be self-found or crafted. Avoid recommending builds that depend "
        "on specific unique items unless they are common drops or target-farmable. "
        "Favour builds that function well with rare gear and deterministic crafting."
    ),
    "hc_ssf": (
        "The player is in HARDCORE SSF — the hardest mode. No trading AND permadeath. "
        "Only recommend extremely tanky, self-sufficient builds. Prioritize defenses "
        "above all else. Gear must be self-crafted. Avoid anything reliant on rare "
        "uniques or that can't survive rippy map mods."
    ),
}

EXP_CONTEXT = {
    "newbie": (
        "The player is NEW to Path of Exile. Explain concepts clearly and avoid "
        "unexplained jargon. When using PoE-specific terms, briefly define them. "
        "Suggest straightforward, beginner-friendly builds. Walk them through "
        "gearing and progression step by step. When they ask vague questions, "
        "guide them with 1-2 clarifying questions before diving in."
    ),
    "casual": (
        "The player is a casual player with basic knowledge. They know core mechanics "
        "but may not be familiar with advanced crafting, atlas strategies, or "
        "min-maxing. Use common PoE terminology but clarify niche concepts. "
        "Ask for context when it would change your recommendation, but keep it brief."
    ),
    "intermediate": (
        "The player is an intermediate player comfortable with endgame content. "
        "You can use standard PoE terminology freely. They understand atlas "
        "strategies, crafting basics, and build planning."
    ),
    "veteran": (
        "The player is a veteran min-maxer. Skip basic explanations. Focus on "
        "optimization, edge cases, niche interactions, and advanced strategies. "
        "They appreciate precise numbers, breakpoints, and deep mechanical analysis. "
        "Give direct answers; only clarify when genuinely ambiguous with multiple "
        "valid approaches."
    ),
}


def build_player_context(settings: dict) -> str:
    """Build the dynamic player profile context appended to every agent primer."""
    league = resolve_league(settings)
    mode = settings.get("mode", "softcore_trade")
    experience = settings.get("experience", "intermediate")

    parts: list[str] = []

    # Temporal grounding
    today = date.today()
    parts.append(f"\nToday's date: **{today.strftime('%B %d, %Y').replace(' 0', ' ')}**")

    entries = _parse_timeline()
    if entries:
        annotated_text, current_league, next_league = _annotate_timeline(entries, today)
        # Use the derived current league if available, fall back to settings
        if current_league:
            league = current_league
        parts.append(
            "\n## Game Timeline (AUTHORITATIVE — overrides your training data)\n"
            "CRITICAL: The timeline below is the ground truth for what has happened in "
            "Path of Exile. Your training data about PoE league dates, names, and content "
            "is WRONG and outdated — do NOT use it. When answering ANY question about "
            "past, current, or upcoming leagues, rely ONLY on this timeline. If a league "
            "is not listed here, you do not know about it — say so and search instead.\n\n" + annotated_text
        )
    else:
        current_league = None
        next_league = None

    # Player profile
    parts.append("\n## Player Profile")
    parts.append(f"- Active league: **{league}** (this is the CURRENT league)")
    if next_league:
        name, version, launch_date = next_league
        friendly_date = launch_date.strftime("%B %d, %Y").replace(" 0", " ")
        parts.append(f"- Next league: **{name}** ({version}) — launches {friendly_date}. NOT YET LIVE.")
    else:
        parts.append("- Next league: not yet announced — search for news.")
    parts.append(f"- When using poe.ninja tools, ALWAYS default to league: {league}")
    parts.append(
        "\n### League Rules (NEVER violate these)\n"
        "- Challenge leagues are ALWAYS fresh starts — NO items, currency, or gear "
        "transfer between challenge leagues. NEVER ask about importing/reusing gear "
        "from a previous league.\n"
        "- When a challenge league ends, characters move to Standard — not to the "
        "next challenge league.\n"
        "- SSF players CANNOT trade. Never suggest trading or ask about trade budget in SSF.\n"
        "- When asking clarifying questions about builds, ask about goals, playstyle, "
        "and time investment — NOT about transferring resources between leagues."
    )
    parts.append(f"\n### Game Mode\n{MODE_CONTEXT.get(mode, '')}")
    parts.append(f"\n### Communication Style\n{EXP_CONTEXT.get(experience, '')}")

    return "\n".join(parts)


def load_prompt(name: str) -> str:
    """Read agents/{name}.md and return its contents."""
    path = _AGENTS_DIR / f"{name}.md"
    return path.read_text(encoding="utf-8")


def build_primer(agent_name: str, settings: dict) -> str:
    """Compose the full system primer: IDENTITY + agent prompt + player context."""
    return "\n\n".join(
        [
            IDENTITY,
            load_prompt(agent_name),
            build_player_context(settings),
        ]
    )
