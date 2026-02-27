from .knowledge import KNOWLEDGE_TOOLS, handle_knowledge_tool
from .poe_ninja import POE_NINJA_TOOLS, handle_poe_ninja_tool
from .web import WEB_TOOLS, handle_web_tool

TOOL_DEFINITIONS = [*POE_NINJA_TOOLS, *WEB_TOOLS, *KNOWLEDGE_TOOLS]

_HANDLERS = {
    "get_currency_prices": handle_poe_ninja_tool,
    "get_item_prices": handle_poe_ninja_tool,
    "poe_web_search": handle_web_tool,
    "read_webpage": handle_web_tool,
    "load_knowledge": handle_knowledge_tool,
    "load_patch_notes": handle_knowledge_tool,
}


def execute_tool(name: str, params: dict, settings: dict):
    handler = _HANDLERS.get(name)
    if handler is None:
        return {"error": f"Unknown tool: {name}"}
    return handler(name, params, settings)
