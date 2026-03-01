import httpx

BASE_URL = "https://poe.ninja/api/data"

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
            "Use when the player asks about currency prices or exchange rates. "
            "Set include_trends to true to get 7-day price trend data."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "enum": CURRENCY_TYPES,
                    "description": (
                        "Currency category: 'Currency' for orbs/scrolls, 'Fragment' for map fragments and splinters."
                    ),
                },
                "league": {
                    "type": "string",
                    "description": "League name. Defaults to POE_LEAGUE env var.",
                },
                "include_trends": {
                    "type": "boolean",
                    "description": (
                        "When true, include 7-day sparkline trend data and percentage change for each currency."
                    ),
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
            "Use to check prices of specific items or browse a category. "
            "Set include_trends to true to get 7-day price trend data."
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
                "include_trends": {
                    "type": "boolean",
                    "description": (
                        "When true, include 7-day sparkline trend data and percentage change for each item."
                    ),
                },
            },
            "required": ["type"],
        },
    },
    {
        "name": "get_build_meta",
        "description": (
            "Get build/meta statistics from poe.ninja: ascendancy popularity, "
            "top skills, popular unique items, and keystones. Use when the player "
            "asks about the current meta, popular builds, class distribution, or "
            "what skills/items people are using."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "league": {
                    "type": "string",
                    "description": "League name. Defaults to POE_LEAGUE env var.",
                },
                "class_filter": {
                    "type": "string",
                    "description": ("Optional ascendancy name to filter results (e.g. 'Juggernaut', 'Necromancer')."),
                },
            },
        },
    },
]

# Cap results sent to the LLM to avoid blowing up context
MAX_RESULTS = 50
MAX_BUILD_META_RESULTS = 15


def _fetch(endpoint: str, params: dict) -> dict:
    with httpx.Client(timeout=10, follow_redirects=True) as client:
        resp = client.get(f"{BASE_URL}/{endpoint}", params=params)
        resp.raise_for_status()
        return resp.json()


def _ranked_list(items: list[dict], cap: int) -> list[dict]:
    """Extract name/count/percentage from items, sort by count desc, and cap."""
    result = [
        {
            "name": i.get("name", "Unknown"),
            "count": i.get("count", 0),
            "percentage": round(i.get("percentage", 0), 2),
        }
        for i in items
    ]
    result.sort(key=lambda x: x["count"], reverse=True)
    return result[:cap]


def _league_slug(league: str) -> str:
    """Convert display league name to URL slug (e.g. 'Settlers of Kalguur' -> 'settlers-of-kalguur')."""
    return league.lower().replace(" ", "-")


def _extract_sparkline(spark_data: dict | None) -> dict | None:
    """Extract trend info from a sparkline object."""
    if not spark_data:
        return None
    points = spark_data.get("data") or []
    change = spark_data.get("totalChange")
    if change is None and not points:
        return None
    result = {}
    if change is not None:
        result["total_change_pct"] = round(change, 2)
    if points:
        result["sparkline"] = [round(p, 2) if p is not None else 0.0 for p in points]
    return result or None


def handle_poe_ninja_tool(name: str, params: dict, settings: dict):
    from poe_copilot.context import resolve_league

    league = params.get("league") or resolve_league(settings)
    include_trends = params.get("include_trends", False)

    try:
        if name == "get_currency_prices":
            item_type = params["type"]
            data = _fetch("currencyoverview", {"league": league, "type": item_type})
            lines = data.get("lines", [])
            results = []
            for line in lines[:MAX_RESULTS]:
                entry = {
                    "name": line["currencyTypeName"],
                    "chaos_equivalent": round(line.get("chaosEquivalent", 0), 2),
                }
                if include_trends:
                    trend = _extract_sparkline(line.get("receiveSparkLine"))
                    if trend:
                        entry["trend"] = trend
                results.append(entry)
            return {
                "league": league,
                "type": item_type,
                "count": len(results),
                "prices": results,
            }

        elif name == "get_item_prices":
            item_type = params["type"]
            data = _fetch("itemoverview", {"league": league, "type": item_type})
            lines = data.get("lines", [])

            name_filter = params.get("name_filter", "").lower()
            if name_filter:
                lines = [line for line in lines if name_filter in line.get("name", "").lower()]

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
                if include_trends:
                    trend = _extract_sparkline(line.get("sparkline"))
                    if trend:
                        entry["trend"] = trend
                results.append(entry)

            return {
                "league": league,
                "type": item_type,
                "count": len(results),
                "items": results,
            }

        elif name == "get_build_meta":
            slug = _league_slug(league)
            data = _fetch(
                "getbuildoverview",
                {"overview": slug, "type": "exp", "language": "en"},
            )

            class_filter = params.get("class_filter", "").lower()
            cap = MAX_BUILD_META_RESULTS

            classes = _ranked_list(data.get("classes", []), cap)

            # Active skills: pre-filter by class before ranking
            skills_raw = data.get("activeSkills", [])
            if class_filter:
                skills_raw = [
                    s
                    for s in skills_raw
                    if any(class_filter in n.get("name", "").lower() for n in s.get("classes", []))
                ]
            active_skills = _ranked_list(skills_raw, cap)

            uniques = _ranked_list(data.get("uniqueItems", []), cap)
            keystones = _ranked_list(data.get("keystones", []), cap)

            result = {
                "league": league,
                "ascendancies": classes,
                "top_skills": active_skills,
                "popular_uniques": uniques,
                "popular_keystones": keystones,
            }
            if class_filter:
                result["filtered_by"] = class_filter
            return result

        return {"error": f"Unknown tool: {name}"}

    except httpx.HTTPStatusError as e:
        error = {
            "error": f"poe.ninja returned HTTP {e.response.status_code}",
            "hint": "Check that the league name is correct.",
        }
        if name == "get_build_meta":
            error["hint"] = (
                "The builds API may be unavailable or the league name "
                "may be wrong. Use poe_web_search to search for current "
                "meta information as a fallback."
            )
        return error
    except httpx.RequestError as e:
        return {"error": f"Could not reach poe.ninja: {e}"}
