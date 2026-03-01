"""Local PoE knowledge-base search tool."""

from pathlib import Path

from poe_copilot.constants import DATABASE_DIR

MAX_ENTRIES = 10
MAX_PATCH_MATCHES = 15

_STRUCTURED_FILES: dict[str, str] = {
    "ascendancy": "ascendancies.txt",
    "currency": "currencies.txt",
    "mechanics": "game_mechanics.txt",
    "gems": "skill_gems.txt",
    "uniques": "unique_items.txt",
}

DATABASE_TOOLS = [
    {
        "name": "query_game_data",
        "description": (
            "Search the local PoE knowledge base for currencies,"
            " ascendancy passives, game mechanics, skill gems,"
            " unique items, and patch notes. Accepts multiple queries in one"
            " call — use this BEFORE web search."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "queries": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "One or more search terms. Each query"
                        " runs independently. Examples:"
                        " ['Divine Orb', 'action speed',"
                        " 'Necromancer']."
                    ),
                },
                "categories": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": [
                            "currency",
                            "ascendancy",
                            "mechanics",
                            "gems",
                            "uniques",
                            "patch_notes",
                        ],
                    },
                    "description": (
                        "Categories to search. Omit to search everything."
                    ),
                },
            },
            "required": ["queries"],
        },
    }
]


def _grep_structured(query: str, filepath: Path) -> list[dict]:
    """Search a pipe-delimited file for matching entries."""
    lines = filepath.read_text(encoding="utf-8").splitlines()
    q = query.lower()

    parsed: list[tuple[str, str, str]] = []
    for line in lines:
        parts = line.split(" | ", maxsplit=2)
        if len(parts) != 3:
            continue
        parsed.append((parts[0], parts[1], parts[2]))

    # Phase 1: name matches → full entities
    matched_names: list[str] = []
    seen: set[str] = set()
    for name, _, _ in parsed:
        if q in name.lower() and name not in seen:
            matched_names.append(name)
            seen.add(name)

    if matched_names:
        entities: dict[str, list[dict]] = {}
        for name, heading, text in parsed:
            if name in seen:
                entities.setdefault(name, []).append(
                    {"heading": heading, "text": text}
                )
        results = [
            {"name": n, "sections": entities[n]}
            for n in matched_names
            if n in entities
        ]
        if len(results) > MAX_ENTRIES:
            return results[:MAX_ENTRIES] + [{"note": "Truncated — narrow query"}]
        return results

    # Phase 2+3: heading matches + content matches (merged)
    # Heading hits are higher relevance, content hits supplement.
    # When any line in a (name, heading) group matches, include
    # ALL lines in that group to preserve complete sections.

    # Build index: (name, heading) → list of line indices
    section_idx: dict[tuple[str, str], list[int]] = {}
    for idx, (name, heading, _) in enumerate(parsed):
        section_idx.setdefault((name, heading), []).append(idx)

    # Collect matched (name, heading) keys, heading first
    matched_sections: list[tuple[str, str]] = []
    seen_sections: set[tuple[str, str]] = set()

    # Heading matches (higher relevance)
    for name, heading, _ in parsed:
        key = (name, heading)
        if key not in seen_sections and q in heading.lower():
            seen_sections.add(key)
            matched_sections.append(key)

    # Content matches (supplement)
    for name, heading, text in parsed:
        key = (name, heading)
        if key not in seen_sections and q in text.lower():
            seen_sections.add(key)
            matched_sections.append(key)

    # Build results: include all lines for each matched section
    hits: dict[str, list[dict]] = {}
    hit_order: list[str] = []
    for key in matched_sections:
        name = key[0]
        if name not in hits:
            hit_order.append(name)
        for idx in section_idx[key]:
            hits.setdefault(name, []).append(
                {"heading": parsed[idx][1], "text": parsed[idx][2]}
            )

    results = [{"name": n, "sections": hits[n]} for n in hit_order]
    if len(results) > MAX_ENTRIES:
        return results[:MAX_ENTRIES] + [{"note": "Truncated — narrow query"}]
    return results


def _grep_patch_notes(query: str, patch_dir: Path) -> list[dict]:
    """Search patch-note files with ±3 lines of context."""
    if not patch_dir.is_dir():
        return []

    q = query.lower()
    results: list[dict] = []

    for vfile in sorted(patch_dir.iterdir()):
        if not vfile.is_file():
            continue
        lines = vfile.read_text(encoding="utf-8").splitlines()

        hits = [i for i, line in enumerate(lines) if q in line.lower()]
        if not hits:
            continue

        # Build and merge context windows
        windows: list[tuple[int, int]] = []
        for i in hits:
            start = max(0, i - 3)
            end = min(len(lines), i + 4)
            if windows and start <= windows[-1][1]:
                windows[-1] = (windows[-1][0], end)
            else:
                windows.append((start, end))

        matches = ["\n".join(lines[s:e]) for s, e in windows]
        entry: dict = {"version": vfile.name}
        if len(matches) > MAX_PATCH_MATCHES:
            entry["matches"] = matches[:MAX_PATCH_MATCHES]
            entry["note"] = "Truncated — narrow query"
        else:
            entry["matches"] = matches
        results.append(entry)

    return results


def _run_query(query: str, categories: list[str] | None) -> dict:
    """Run a single query against selected categories."""
    result: dict = {}

    if categories is None:
        files = _STRUCTURED_FILES
    else:
        files = {k: v for k, v in _STRUCTURED_FILES.items() if k in categories}

    for cat, filename in files.items():
        filepath = DATABASE_DIR / filename
        if not filepath.exists():
            continue
        hits = _grep_structured(query, filepath)
        if hits:
            result[cat] = hits

    if categories is None or "patch_notes" in categories:
        patch_dir = DATABASE_DIR / "patch_notes"
        hits = _grep_patch_notes(query, patch_dir)
        if hits:
            result["patch_notes"] = hits

    return result


def handle_database_tool(name: str, params: dict, settings: dict) -> dict:
    """Search the local PoE knowledge base.

    Parameters
    ----------
    name : str
        Tool name (``"query_game_data"``).
    params : dict
        Must contain ``"queries"`` list; optional
        ``"categories"``.
    settings : dict
        User settings (unused, kept for handler protocol).

    Returns
    -------
    dict
        Results keyed by query string.
    """
    queries: list[str] = params["queries"]
    categories = params.get("categories")
    return {q: _run_query(q, categories) for q in queries}
