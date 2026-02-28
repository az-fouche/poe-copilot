from pathlib import Path

_DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data"
PATCH_NOTES_DIR = _DATA_DIR / "patch_notes"

KNOWLEDGE_TOOLS = [
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
