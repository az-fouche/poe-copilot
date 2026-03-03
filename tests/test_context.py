"""Tests for poe_copilot/context.py."""

from datetime import date
from unittest.mock import patch

from poe_copilot.core.context import (
    _annotate_timeline,
    _load_identity,
    _parse_timeline,
    build_player_context,
    build_primer,
    load_check_loadout,
    load_loadout,
)

# ── _parse_timeline ───────────────────────────────────────────────────────


@patch("poe_copilot.core.context._load_timeline")
def test_parse_timeline_normal(mock_load):
    mock_load.return_value = "2024-07-26 — 3.25 Settlers league launch.\n2025-10-31 — 3.27 Keepers league launch."
    entries = _parse_timeline()
    assert len(entries) == 2
    assert entries[0][0] == date(2024, 7, 26)
    assert entries[0][1] == "Settlers"
    assert entries[1][0] == date(2025, 10, 31)
    assert entries[1][1] == "Keepers"


@patch("poe_copilot.core.context._load_timeline")
def test_parse_timeline_no_league_name(mock_load):
    mock_load.return_value = (
        "2024-07-26 — some patch note without league keyword"
    )
    entries = _parse_timeline()
    assert len(entries) == 1
    assert entries[0][0] == date(2024, 7, 26)
    assert entries[0][1] is None


@patch("poe_copilot.core.context._load_timeline")
def test_parse_timeline_empty_file(mock_load):
    mock_load.return_value = ""
    entries = _parse_timeline()
    assert entries == []


@patch("poe_copilot.core.context._load_timeline")
def test_parse_timeline_skips_non_date_lines(mock_load):
    mock_load.return_value = (
        "## Leagues history\n2024-07-26 — 3.25 Settlers league launch."
    )
    entries = _parse_timeline()
    assert len(entries) == 1


# ── _annotate_timeline ────────────────────────────────────────────────────


def test_annotate_past_entry_unchanged():
    entries = [
        (
            date(2024, 7, 26),
            "Settlers",
            "2024-07-26 — 3.25 Settlers league launched.",
        )
    ]
    text, current, next_l = _annotate_timeline(entries, today=date(2025, 1, 1))  # type: ignore
    assert "2024-07-26" in text
    assert "NOT YET LIVE" not in text


def test_annotate_future_entry_marked():
    entries = [
        (date(2026, 3, 6), "Mirage", "2026-03-06 — 3.28 Mirage league launched.")
    ]
    text, current, next_l = _annotate_timeline(entries, today=date(2025, 12, 1))  # type: ignore
    assert "launches" in text
    assert text.strip().endswith("\u26a0\ufe0f NOT YET LIVE")


def test_annotate_derives_current_league():
    entries = [
        (
            date(2024, 7, 26),
            "Settlers",
            "2024-07-26 — 3.25 Settlers league launch.",
        ),
        (
            date(2025, 10, 31),
            "Keepers",
            "2025-10-31 — 3.27 Keepers league launch.",
        ),
    ]
    _, current, _ = _annotate_timeline(entries, today=date(2026, 1, 1))  # type: ignore
    assert current == "Keepers"


def test_annotate_derives_next_league():
    entries = [
        (
            date(2025, 10, 31),
            "Keepers",
            "2025-10-31 — 3.27 Keepers league launch.",
        ),
        (
            date(2026, 3, 6),
            "Mirage",
            "2026-03-06 — 3.28 Mirage league launched.",
        ),
    ]
    _, _, next_l = _annotate_timeline(entries, today=date(2026, 1, 1))  # type: ignore
    assert next_l is not None
    assert next_l[0] == "Mirage"
    assert next_l[1] == "3.28"
    assert next_l[2] == date(2026, 3, 6)


# ── build_player_context ─────────────────────────────────────────────────


@patch("poe_copilot.core.context._parse_timeline", return_value=[])
@patch("poe_copilot.core.context.date")
def test_player_context_includes_date(mock_date, mock_timeline):
    mock_date.today.return_value = date(2026, 3, 1)
    mock_date.fromisoformat = date.fromisoformat
    result = build_player_context(
        {
            "league": "Keepers",
            "mode": "softcore_trade",
            "experience": "intermediate",
        }
    )
    assert "March 1, 2026" in result


@patch("poe_copilot.core.context._parse_timeline", return_value=[])
@patch("poe_copilot.core.context.date")
def test_player_context_mode_injected(mock_date, mock_timeline):
    mock_date.today.return_value = date(2026, 3, 1)
    mock_date.fromisoformat = date.fromisoformat
    result = build_player_context(
        {"league": "Keepers", "mode": "hc_ssf", "experience": "intermediate"}
    )
    assert "HARDCORE SSF" in result


@patch("poe_copilot.core.context._parse_timeline", return_value=[])
@patch("poe_copilot.core.context.date")
def test_player_context_experience_injected(mock_date, mock_timeline):
    mock_date.today.return_value = date(2026, 3, 1)
    mock_date.fromisoformat = date.fromisoformat
    result = build_player_context(
        {"league": "Keepers", "mode": "softcore_trade", "experience": "veteran"}
    )
    assert "veteran" in result.lower() or "min-max" in result.lower()


# ── pre-launch promotion ────────────────────────────────────────────────

TIMELINE_ENTRIES = [
    (
        date(2025, 10, 31),
        "Keepers",
        "2025-10-31 — 3.27 Keepers league launch.",
    ),
    (
        date(2026, 3, 6),
        "Mirage",
        "2026-03-06 — 3.28 Mirage league launched.",
    ),
]


@patch("poe_copilot.core.context._parse_timeline")
@patch("poe_copilot.core.context.date")
def test_pre_launch_promotes_upcoming_league(mock_date, mock_timeline):
    """3 days before Mirage launch: Mirage is THE league."""
    mock_date.today.return_value = date(2026, 3, 3)
    mock_date.fromisoformat = date.fromisoformat
    mock_timeline.return_value = TIMELINE_ENTRIES
    result = build_player_context(
        {
            "league": "challenge",
            "mode": "softcore_trade",
            "experience": "intermediate",
        }
    )
    assert "Active league: **Mirage**" in result


@patch("poe_copilot.core.context._parse_timeline")
@patch("poe_copilot.core.context.date")
def test_pre_launch_ninja_uses_live_league(mock_date, mock_timeline):
    """poe.ninja should still target the live league."""
    mock_date.today.return_value = date(2026, 3, 3)
    mock_date.fromisoformat = date.fromisoformat
    mock_timeline.return_value = TIMELINE_ENTRIES
    result = build_player_context(
        {
            "league": "challenge",
            "mode": "softcore_trade",
            "experience": "intermediate",
        }
    )
    assert "default to league: Keepers" in result


@patch("poe_copilot.core.context._parse_timeline")
@patch("poe_copilot.core.context.date")
def test_pre_launch_shows_note(mock_date, mock_timeline):
    """Pre-launch mode note is injected."""
    mock_date.today.return_value = date(2026, 3, 3)
    mock_date.fromisoformat = date.fromisoformat
    mock_timeline.return_value = TIMELINE_ENTRIES
    result = build_player_context(
        {
            "league": "challenge",
            "mode": "softcore_trade",
            "experience": "intermediate",
        }
    )
    assert "PRE-LAUNCH MODE" in result


@patch("poe_copilot.core.context._parse_timeline")
@patch("poe_copilot.core.context.date")
def test_no_pre_launch_when_far_from_next(mock_date, mock_timeline):
    """15+ days before launch: no promotion, Keepers is active."""
    mock_date.today.return_value = date(2026, 2, 1)
    mock_date.fromisoformat = date.fromisoformat
    mock_timeline.return_value = TIMELINE_ENTRIES
    result = build_player_context(
        {
            "league": "challenge",
            "mode": "softcore_trade",
            "experience": "intermediate",
        }
    )
    assert "Active league: **Keepers**" in result
    assert "PRE-LAUNCH MODE" not in result


# ── build_primer ──────────────────────────────────────────────────────────


@patch(
    "poe_copilot.core.context.build_player_context",
    return_value="[player context]",
)
@patch("poe_copilot.core.context.load_prompt", return_value="[router prompt]")
def test_build_primer_structure(mock_prompt, mock_ctx):
    result = build_primer("router", {"league": "Keepers"})
    assert result.startswith(_load_identity())
    assert "[router prompt]" in result
    assert "[player context]" in result


# ── load_loadout ─────────────────────────────────────────────────────────


def test_load_loadout_returns_content():
    content = load_loadout("builds")
    assert "Build Mechanics Analysis" in content
    assert "Build Research Patterns" in content


def test_load_loadout_missing_returns_empty():
    result = load_loadout("nonexistent_loadout_xyz")
    assert result == ""


# ── load_check_loadout ──────────────────────────────────────────────────


def test_load_check_loadout_returns_content():
    content = load_check_loadout("builds")
    assert "Build-Specific Checks" in content
    assert "Support gem tags" in content


def test_load_check_loadout_missing_returns_empty():
    result = load_check_loadout("nonexistent_loadout_xyz")
    assert result == ""


def test_load_check_loadout_none_returns_empty():
    result = load_check_loadout(None)
    assert result == ""
