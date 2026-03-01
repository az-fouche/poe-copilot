from .poe_ninja import POE_NINJA_TOOLS, handle_poe_ninja_tool
from .web import WEB_TOOLS, handle_web_tool

TOOL_DEFINITIONS = [*POE_NINJA_TOOLS, *WEB_TOOLS]

_HANDLERS = {
    "get_currency_prices": handle_poe_ninja_tool,
    "get_item_prices": handle_poe_ninja_tool,
    "get_build_meta": handle_poe_ninja_tool,
    "poe_web_search": handle_web_tool,
    "read_webpage": handle_web_tool,
}
