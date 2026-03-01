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


# --- Phase 4: keyword AND matching ---

UNIQUES = DATABASE_DIR / "unique_items.txt"


def test_keyword_match_finds_scattered_terms():
    """Multi-keyword query finds entity with words scattered across content."""
    results = _grep_structured("strength dexterity intelligence", UNIQUES)
    names = {r["name"] for r in results if "name" in r}
    assert "Black Sun Crest" in names
    # Should return all sections for the matched entity
    entry = next(r for r in results if r["name"] == "Black Sun Crest")
    assert len(entry["sections"]) > 1


def test_keyword_match_skipped_when_earlier_phase_hits(tmp_path):
    """Exact substring match takes priority over keyword AND matching."""
    f = tmp_path / "test.txt"
    f.write_text(
        "Alpha | Info | contains foo and bar here\n"
        "Beta | Info | has foo bar as substring\n",
        encoding="utf-8",
    )
    # "foo bar" is an exact substring in Beta's content
    results = _grep_structured("foo bar", f)
    names = [r["name"] for r in results]
    # Phase 2/3 content match should find both
    assert "Beta" in names


def test_keyword_match_filters_stopwords(tmp_path):
    """Stopwords and short tokens are filtered from keywords."""
    f = tmp_path / "test.txt"
    f.write_text(
        "Item | Info | increases strength and dexterity\n"
        "Other | Info | unrelated content here\n",
        encoding="utf-8",
    )
    # "the" and "and" are stopwords, "of" is < 3 chars
    results = _grep_structured("the strength and dexterity", f)
    assert len(results) == 1
    assert results[0]["name"] == "Item"


def test_keyword_match_needs_all_keywords(tmp_path):
    """All keywords must appear — partial overlap is not enough."""
    f = tmp_path / "test.txt"
    f.write_text(
        "Item | Info | has strength but not the other\n",
        encoding="utf-8",
    )
    results = _grep_structured("strength dexterity intelligence", f)
    assert results == []


def test_keyword_match_single_keyword_skipped(tmp_path):
    """Single keyword after filtering does not trigger Phase 4."""
    f = tmp_path / "test.txt"
    f.write_text(
        "Item | Info | has strength modifier\n",
        encoding="utf-8",
    )
    # "the" is a stopword → only "strength" remains → < 2 keywords
    results = _grep_structured("the strength", f)
    assert results == []


def test_keyword_match_truncation(tmp_path):
    """Keyword match respects MAX_ENTRIES truncation."""
    lines = [
        f"Entity{i} | Info | has alpha beta gamma\n"
        for i in range(MAX_ENTRIES + 5)
    ]
    f = tmp_path / "big.txt"
    f.write_text("".join(lines), encoding="utf-8")

    results = _grep_structured("alpha beta gamma", f)
    assert len(results) == MAX_ENTRIES + 1
    assert results[-1] == {"note": "Truncated — narrow query"}


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
            "categories": ["currency"],
        },
        SETTINGS,
    )
    assert "Divine Orb" in result
    assert "Exalted Orb" in result
    assert "currency" in result["Divine Orb"]
    assert "currency" in result["Exalted Orb"]


def test_category_filter_skips_others():
    """categories=['currency'] does not search patch_notes."""
    result = handle_database_tool(
        "query_game_data",
        {
            "queries": ["Necromancer"],
            "categories": ["currency"],
        },
        SETTINGS,
    )
    necro = result["Necromancer"]
    assert "patch_notes" not in necro


def test_single_category_searches_only_that():
    """categories=['ascendancy'] skips patch_notes."""
    result = handle_database_tool(
        "query_game_data",
        {
            "queries": ["Necromancer"],
            "categories": ["ascendancy"],
        },
        SETTINGS,
    )
    necro = result["Necromancer"]
    assert "ascendancy" in necro
    assert "patch_notes" not in necro


def test_default_category_is_all():
    """Omitting category defaults to 'all'."""
    result = handle_database_tool(
        "query_game_data",
        {"queries": ["Divine Orb"]},
        SETTINGS,
    )
    divine = result["Divine Orb"]
    assert "currency" in divine


def test_multi_category_searches_subset():
    """categories=['gems','patch_notes'] skips others."""
    result = handle_database_tool(
        "query_game_data",
        {
            "queries": ["Necromancer"],
            "categories": ["gems", "patch_notes"],
        },
        SETTINGS,
    )
    necro = result["Necromancer"]
    assert "ascendancy" not in necro
    assert "currency" not in necro
    # patch_notes should be searched
    assert "patch_notes" in necro


def test_no_results_returns_empty_dict():
    """Query with no hits returns empty dict per query."""
    result = handle_database_tool(
        "query_game_data",
        {"queries": ["xyznonexistent"]},
        SETTINGS,
    )
    assert result["xyznonexistent"] == {}
