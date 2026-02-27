from .poe_ninja import POE_NINJA_TOOLS, handle_poe_ninja_tool

TOOL_DEFINITIONS = [*POE_NINJA_TOOLS]

_HANDLERS = {
    "get_currency_prices": handle_poe_ninja_tool,
    "get_item_prices": handle_poe_ninja_tool,
}


def execute_tool(name: str, params: dict):
    handler = _HANDLERS.get(name)
    if handler is None:
        return {"error": f"Unknown tool: {name}"}
    return handler(name, params)
