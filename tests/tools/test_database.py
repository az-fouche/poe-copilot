"""Tests for poe_copilot/tools/database.py.

All tests read the real bundled database files — no mocking.
"""

from poe_copilot.tools.database import (
    MAX_ENTRIES,
    _grep_patch_notes,
    _grep_structured,
    handle_database_tool,
)
from poe_copilot.constants import DATABASE_DIR


CURRENCIES = DATABASE_DIR / "currencies.txt"
ASCENDANCIES = DATABASE_DIR / "ascendancies.txt"
MECHANICS = DATABASE_DIR / "game_mechanics.txt"
PATCH_DIR = DATABASE_DIR / "patch_notes"
SETTINGS: dict = {}


# --- _grep_structured ---


def test_name_match_returns_full_entry():
    """Name match collects ALL sections for that entity."""
    results = _grep_structured("Divine Orb", CURRENCIES)
    assert len(results) >= 1
    entry = results[0]
    assert entry["name"] == "Divine Orb"
    headings = {s["heading"] for s in entry["sections"]}
    assert "Infobox" in headings
    assert len(entry["sections"]) > 1


def test_substring_name_match():
    """Partial name matches multiple entities."""
    results = _grep_structured("Orb", CURRENCIES)
    names = {r["name"] for r in results if "name" in r}
    assert len(names) > 1


def test_case_insensitive_name():
    """Lower-case query matches title-case name."""
    results = _grep_structured("divine orb", CURRENCIES)
    assert any(r.get("name") == "Divine Orb" for r in results)


def test_heading_match():
    """Query matching a section heading returns those sections."""
    # "Damage conversion" is a heading under "Game mechanics"
    results = _grep_structured("Damage conversion", MECHANICS)
    assert len(results) >= 1
    entry = results[0]
    assert entry["name"] == "Game mechanics"
    headings = {s["heading"] for s in entry["sections"]}
    assert "Damage conversion" in headings


def test_heading_match_ordered_before_content(tmp_path):
    """Heading hits appear before content-only hits."""
    f = tmp_path / "test.txt"
    f.write_text(
        "Alpha | Topic X | text about unrelated\n"
        "Beta | Unrelated | mentions topic x here\n",
        encoding="utf-8",
    )
    results = _grep_structured("Topic X", f)
    # Both should appear: Alpha via heading, Beta via content
    names = [r["name"] for r in results]
    assert names == ["Alpha", "Beta"]


def test_heading_and_content_deduped(tmp_path):
    """Same section isn't returned twice if it matches both."""
    f = tmp_path / "test.txt"
    f.write_text(
        "Ent | Topic Y | topic y details here\n",
        encoding="utf-8",
    )
    results = _grep_structured("Topic Y", f)
    assert len(results) == 1
    assert len(results[0]["sections"]) == 1


def test_content_fallback():
    """Term absent from names and headings but in content."""
    # "re-roll" appears in currency content but not as a
    # currency name or heading
    results = _grep_structured("re-roll", CURRENCIES)
    assert len(results) >= 1
    # Content-only matches return single-section entries
    for r in results:
        if "sections" in r:
            assert len(r["sections"]) >= 1


def test_no_match():
    """Nonsense query returns empty list."""
    results = _grep_structured("xyznonexistent", CURRENCIES)
    assert results == []


def test_malformed_lines_skipped(tmp_path):
    """Lines without 3 pipe parts don't crash."""
    bad_file = tmp_path / "bad.txt"
    bad_file.write_text(
        "Good Name | Section | Content text\n"
        "bad line without pipes\n"
        "also bad | only two parts\n"
        "Another | Info | Entry here\n",
        encoding="utf-8",
    )
    # Both valid lines are found, malformed lines ignored
    results = _grep_structured("Good Name", bad_file)
    assert len(results) == 1
    assert results[0]["name"] == "Good Name"
    results2 = _grep_structured("Another", bad_file)
    assert len(results2) == 1
    assert results2[0]["name"] == "Another"


def test_truncation_structured(tmp_path):
    """Broad query exceeding MAX_ENTRIES adds note."""
    lines = [
        f"Entity{i} | Info | Content about topic\n"
        for i in range(MAX_ENTRIES + 5)
    ]
    big_file = tmp_path / "big.txt"
    big_file.write_text("".join(lines), encoding="utf-8")

    results = _grep_structured("Entity", big_file)
    assert len(results) == MAX_ENTRIES + 1
    assert results[-1] == {"note": "Truncated — narrow query"}


# --- _grep_patch_notes ---


def test_patch_notes_search():
    """Query hitting patch notes returns context windows."""
    results = _grep_patch_notes("Necromancer", PATCH_DIR)
    assert len(results) >= 1
    entry = results[0]
    assert "version" in entry
    assert "matches" in entry
    assert len(entry["matches"]) >= 1
    # Context should include surrounding lines
    block = entry["matches"][0]
    assert "Necromancer" in block


def test_patch_notes_no_match():
    """Nonsense query returns empty list."""
    results = _grep_patch_notes("xyznonexistent", PATCH_DIR)
    assert results == []


def test_patch_notes_missing_dir(tmp_path):
    """Non-existent directory returns empty list."""
    results = _grep_patch_notes("anything", tmp_path / "nope")
    assert results == []


# --- handle_database_tool (integration) ---


def test_multi_query_batching():
    """Multiple queries return results keyed by each."""
    result = handle_database_tool(
        "query_game_data",
        {
            "queries": ["Divine Orb", "Exalted Orb"],
            "category": "currency",
        },
        SETTINGS,
    )
    assert "Divine Orb" in result
    assert "Exalted Orb" in result
    assert "currency" in result["Divine Orb"]
    assert "currency" in result["Exalted Orb"]


def test_category_filter_skips_others():
    """category='currency' does not search patch_notes."""
    result = handle_database_tool(
        "query_game_data",
        {
            "queries": ["Necromancer"],
            "category": "currency",
        },
        SETTINGS,
    )
    necro = result["Necromancer"]
    assert "patch_notes" not in necro


def test_category_all_searches_everything():
    """category='all' searches structured + patch notes."""
    result = handle_database_tool(
        "query_game_data",
        {
            "queries": ["Necromancer"],
            "category": "all",
        },
        SETTINGS,
    )
    necro = result["Necromancer"]
    assert "ascendancy" in necro


def test_default_category_is_all():
    """Omitting category defaults to 'all'."""
    result = handle_database_tool(
        "query_game_data",
        {"queries": ["Divine Orb"]},
        SETTINGS,
    )
    divine = result["Divine Orb"]
    assert "currency" in divine


def test_no_results_returns_empty_dict():
    """Query with no hits returns empty dict per query."""
    result = handle_database_tool(
        "query_game_data",
        {"queries": ["xyznonexistent"]},
        SETTINGS,
    )
    assert result["xyznonexistent"] == {}
