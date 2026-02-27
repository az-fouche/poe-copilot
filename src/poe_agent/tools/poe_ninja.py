import os

import httpx

BASE_URL = "https://poe.ninja/api/data"


def _default_league() -> str:
    return os.environ.get("POE_LEAGUE", "Standard")

CURRENCY_TYPES = ["Currency", "Fragment"]
ITEM_TYPES = [
    "Oil",
    "Incubator",
    "Scarab",
    "Fossil",
    "Resonator",
    "Essence",
    "DivinationCard",
    "SkillGem",
    "BaseType",
    "UniqueMap",
    "Map",
    "UniqueJewel",
    "UniqueFlask",
    "UniqueWeapon",
    "UniqueArmour",
    "UniqueAccessory",
    "Beast",
]

POE_NINJA_TOOLS = [
    {
        "name": "get_currency_prices",
        "description": (
            "Get current currency exchange rates from poe.ninja. "
            "Returns chaos-equivalent values for currencies and fragments. "
            "Use when the player asks about currency prices or exchange rates."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "enum": CURRENCY_TYPES,
                    "description": (
                        "Currency category: 'Currency' for orbs/scrolls, "
                        "'Fragment' for map fragments and splinters."
                    ),
                },
                "league": {
                    "type": "string",
                    "description": "League name. Defaults to POE_LEAGUE env var.",
                },
            },
            "required": ["type"],
        },
    },
    {
        "name": "get_item_prices",
        "description": (
            "Get current item prices from poe.ninja in chaos orb equivalent. "
            "Supports uniques, gems, div cards, maps, fossils, essences, etc. "
            "Use to check prices of specific items or browse a category."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "enum": ITEM_TYPES,
                    "description": "Item category to look up.",
                },
                "league": {
                    "type": "string",
                    "description": "League name. Defaults to POE_LEAGUE env var.",
                },
                "name_filter": {
                    "type": "string",
                    "description": (
                        "Filter results by item name (case-insensitive substring). "
                        "Use to find a specific item without browsing the full list."
                    ),
                },
            },
            "required": ["type"],
        },
    },
]

# Cap results sent to the LLM to avoid blowing up context
MAX_RESULTS = 50


def _fetch(endpoint: str, params: dict) -> dict:
    with httpx.Client(timeout=10, follow_redirects=True) as client:
        resp = client.get(f"{BASE_URL}/{endpoint}", params=params)
        resp.raise_for_status()
        return resp.json()


def handle_poe_ninja_tool(name: str, params: dict):
    league = params.get("league", _default_league())
    item_type = params["type"]

    try:
        if name == "get_currency_prices":
            data = _fetch(
                "currencyoverview", {"league": league, "type": item_type}
            )
            lines = data.get("lines", [])
            results = [
                {
                    "name": line["currencyTypeName"],
                    "chaos_equivalent": round(
                        line.get("chaosEquivalent", 0), 2
                    ),
                }
                for line in lines[:MAX_RESULTS]
            ]
            return {
                "league": league,
                "type": item_type,
                "count": len(results),
                "prices": results,
            }

        elif name == "get_item_prices":
            data = _fetch(
                "itemoverview", {"league": league, "type": item_type}
            )
            lines = data.get("lines", [])

            name_filter = params.get("name_filter", "").lower()
            if name_filter:
                lines = [
                    l
                    for l in lines
                    if name_filter in l.get("name", "").lower()
                ]

            results = []
            for line in lines[:MAX_RESULTS]:
                entry = {
                    "name": line.get("name", "Unknown"),
                    "chaos_value": round(line.get("chaosValue", 0), 1),
                    "divine_value": round(line.get("divineValue", 0), 2),
                }
                if "links" in line:
                    entry["links"] = line["links"]
                if line.get("variant"):
                    entry["variant"] = line["variant"]
                if "gemLevel" in line:
                    entry["gem_level"] = line["gemLevel"]
                    entry["gem_quality"] = line.get("gemQuality", 0)
                results.append(entry)

            return {
                "league": league,
                "type": item_type,
                "count": len(results),
                "items": results,
            }

        return {"error": f"Unknown tool: {name}"}

    except httpx.HTTPStatusError as e:
        return {
            "error": f"poe.ninja returned HTTP {e.response.status_code}",
            "hint": "Check that the league name is correct.",
        }
    except httpx.RequestError as e:
        return {"error": f"Could not reach poe.ninja: {e}"}
