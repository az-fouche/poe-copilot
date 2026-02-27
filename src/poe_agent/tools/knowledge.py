from pathlib import Path

_DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data"
TOPICS_DIR = _DATA_DIR / "topics"
PATCH_NOTES_DIR = _DATA_DIR / "patch_notes"

KNOWLEDGE_TOOLS = [
    {
        "name": "load_knowledge",
        "description": (
            "Load detailed reference material about a PoE topic. Use this when "
            "you need in-depth knowledge about a specific game system to answer "
            "the player's question. Available topics are listed in your system prompt."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "The topic identifier to load (e.g. 'gear_and_crafting', 'defenses')",
                }
            },
            "required": ["topic"],
        },
    },
    {
        "name": "load_patch_notes",
        "description": (
            "Load curated patch notes for a specific PoE league/patch. Use this "
            "when the player asks about balance changes, new mechanics, skill "
            "reworks, or what changed in a specific league. Available patches are "
            "listed in your system prompt."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "patch": {
                    "type": "string",
                    "description": "The patch identifier to load (e.g. '3.25_keepers')",
                }
            },
            "required": ["patch"],
        },
    },
]


def handle_knowledge_tool(name: str, params: dict, settings: dict) -> dict:
    if name == "load_patch_notes":
        return _load_patch_notes(params)
    topic = params.get("topic", "")
    if not topic:
        return {"error": "Missing required parameter: topic"}
    topic_file = TOPICS_DIR / f"{topic}.md"
    if not topic_file.exists():
        available = [f.stem for f in sorted(TOPICS_DIR.glob("*.md"))]
        return {"error": f"Unknown topic: '{topic}'", "available_topics": available}
    content = topic_file.read_text(encoding="utf-8").strip()
    return {"topic": topic, "content": content}


def _load_patch_notes(params: dict) -> dict:
    patch = params.get("patch", "")
    if not patch:
        return {"error": "Missing required parameter: patch"}
    patch_file = PATCH_NOTES_DIR / f"{patch}.md"
    if not patch_file.exists():
        available = [f.stem for f in sorted(PATCH_NOTES_DIR.glob("*.md"))]
        if not available:
            return {"error": "No patch notes available yet. Use poe_web_search to find patch notes online."}
        return {"error": f"Unknown patch: '{patch}'", "available_patches": available}
    content = patch_file.read_text(encoding="utf-8").strip()
    return {"patch": patch, "content": content}
