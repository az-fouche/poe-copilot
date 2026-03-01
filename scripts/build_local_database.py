"""Scrape the PoE wiki and build local plain-text databases.

Usage
-----
    uv run python scripts/build_local_database.py            # all
    uv run python scripts/build_local_database.py --limit 10 # 10 pages per category
"""

import argparse
import asyncio
import re
import sys
from pathlib import Path

import httpx
from bs4 import BeautifulSoup
from tqdm import tqdm

API_URL = "https://www.poewiki.net/w/api.php"

OUTPUT_DIR = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "poe_copilot"
    / "assets"
    / "database"
)

# Map output filename -> list of wiki categories to merge.
# Extend this dict to scrape more categories.
CATEGORIES: dict[str, list[str]] = {
    "currencies.txt": ["Currency items"],
    "game_mechanics.txt": ["Game mechanics"],
    "ascendancies.txt": [
        "Ascendancy classes",
        "Ascendancy notable passive skills",
    ],
    "passive_skills.txt": [
        "Notable passive skills",
        "Keystone passive skills",
        "Mastery data",
    ],
    "skill_gems.txt": [
        "Strength skill gems",
        "Dexterity skill gems",
        "Intelligence skill gems",
        "White skill gems",
    ],
    "unique_items.txt": [
        "Unique items",
        "Unique item pieces",
        # Armour & accessories
        "Unique body armours",
        "Unique helmets",
        "Unique gloves",
        "Unique boots",
        "Unique shields",
        "Unique amulets",
        "Unique rings",
        "Unique belts",
        "Unique quivers",
        "Unique jewels",
        "Unique abyss jewels",
        "Unique idols",
        "Unique relics",
        # Weapons
        "Unique bows",
        "Unique claws",
        "Unique daggers",
        "Unique rune daggers",
        "Unique one-handed swords",
        "Unique thrusting one-handed swords",
        "Unique two-handed swords",
        "Unique one-handed axes",
        "Unique two-handed axes",
        "Unique one-handed maces",
        "Unique two-handed maces",
        "Unique sceptres",
        "Unique staves",
        "Unique warstaves",
        "Unique wands",
        # Flasks & other
        "Unique life flasks",
        "Unique mana flasks",
        "Unique hybrid flasks",
        "Unique utility flasks",
        "Unique maps",
        "Unique contracts",
        "Unique tinctures",
        "Unique fishing rods",
    ],
}

MAX_CONCURRENT = 5
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

_WHITESPACE_JUNK = re.compile(r"[\s]+")
_SPACE_DOT = re.compile(r" \.")
_MULTI_DOTS = re.compile(r"\.{2,}")
_ASCENDANCY_NOTABLE = re.compile(
    r"notable [Aa]scendancy passive skill for the (.+?)\."
)


# -- Wiki API helpers ------------------------------------------------


async def _fetch_category_titles(
    client: httpx.AsyncClient,
    category: str,
    limit: int | None,
) -> list[str]:
    """Return page titles in *category* via the MediaWiki API."""
    titles: list[str] = []
    params: dict[str, str | int] = {
        "action": "query",
        "list": "categorymembers",
        "cmtitle": f"Category:{category}",
        "cmlimit": 500,
        "format": "json",
        "maxlag": 5,
    }

    while True:
        resp = await _get_with_maxlag(client, params)
        data = resp.json()
        for member in data.get("query", {}).get("categorymembers", []):
            titles.append(member["title"])
            if limit and len(titles) >= limit:
                return titles

        cont = data.get("continue", {}).get("cmcontinue")
        if not cont:
            break
        params["cmcontinue"] = cont

    return titles


async def _fetch_page_html(
    client: httpx.AsyncClient,
    title: str,
    *,
    retries: int = 3,
) -> str | None:
    """Fetch parsed HTML for *title* with retries on transient errors."""
    params: dict[str, str | int] = {
        "action": "parse",
        "page": title,
        "prop": "text",
        "format": "json",
        "maxlag": 5,
    }
    for attempt in range(retries):
        try:
            resp = await _get_with_maxlag(client, params)
            data = resp.json()
            return str(data["parse"]["text"]["*"])
        except (httpx.HTTPStatusError, KeyError, ValueError):
            if attempt < retries - 1:
                await asyncio.sleep(2 * (attempt + 1))
                continue
            print(f"  SKIP {title} (after {retries} attempts)", file=sys.stderr)
            return None
    return None


async def _get_with_maxlag(
    client: httpx.AsyncClient,
    params: dict[str, str | int],
) -> httpx.Response:
    """GET with one retry on maxlag error."""
    resp = await client.get(API_URL, params=params)
    if resp.status_code == 429 or "maxlag" in resp.text[:200]:
        await asyncio.sleep(5)
        resp = await client.get(API_URL, params=params)
    resp.raise_for_status()
    return resp


# -- HTML cleanup ----------------------------------------------------


_SKIP_SECTIONS = frozenset(
    {
        "Contents",
        "Version history",
        "References",
        "External links",
        "See also",
        "Video",
    }
)


def _scrub(text: str) -> str:
    """Collapse whitespace and fix wiki punctuation artifacts."""
    text = _WHITESPACE_JUNK.sub(" ", text)
    text = _SPACE_DOT.sub(".", text)
    text = _MULTI_DOTS.sub(".", text)
    return text.strip()


def _clean_html(html: str, title: str) -> str:
    """Extract grep-friendly lines: ``Title | Section | text``.

    One line per paragraph, prefixed with item name and section.
    """
    soup = BeautifulSoup(html, "html.parser")
    lines: list[str] = []

    # -- Infobox --
    ib = soup.find(class_="infobox-page-container")
    if ib:
        groups = [
            g.get_text(" ", strip=True)
            for g in ib.select(".group")
            if not g.get_text(strip=True).startswith("Metadata")
        ]
        if groups:
            lines.append(f"{title} | Infobox | {_scrub('. '.join(groups))}")
        ib.decompose()

    # -- Strip noise --
    for el in soup.select(".c-item-hoverbox"):
        a = el.find("a")
        el.replace_with(a.get_text() if a else "")
    for el in soup.select(".mw-editsection"):
        el.decompose()

    # -- Walk sections --
    container = soup.select_one(".mw-parser-output")
    if not container:
        return "\n".join(lines)

    section = "Description"
    skip = False
    for child in container.children:
        tag = getattr(child, "name", None)
        if tag in ("h2", "h3"):
            section = child.get_text(strip=True)
            skip = section in _SKIP_SECTIONS
            continue
        if skip:
            continue
        if tag == "p":
            text = _scrub(child.get_text(" ", strip=True))
            if text:
                lines.append(f"{title} | {section} | {text}")

    # Prefix ascendancy notables with class name
    for line in lines:
        m = _ASCENDANCY_NOTABLE.search(line)
        if m:
            asc = m.group(1)
            lines = [
                ln.replace(f"{title} |", f"{asc} | {title} |", 1) for ln in lines
            ]
            break

    return "\n".join(lines)


# -- Main pipeline ---------------------------------------------------


async def _build_file(
    client: httpx.AsyncClient,
    filename: str,
    wiki_categories: list[str],
    limit: int | None,
    semaphore: asyncio.Semaphore,
) -> None:
    """Fetch all pages for *wiki_categories* and write *filename*."""
    # Gather titles from all categories
    titles: list[str] = []
    for cat in wiki_categories:
        print(f"  Fetching titles from Category:{cat}...")
        titles.extend(await _fetch_category_titles(client, cat, limit))

    if not titles:
        print(f"  No pages found, skipping {filename}.")
        return

    # Fetch pages concurrently
    pages: dict[str, str] = {}
    bar = tqdm(total=len(titles), desc=f"  {filename}", unit="pg")

    async def _fetch_one(t: str) -> None:
        async with semaphore:
            html = await _fetch_page_html(client, t)
            if html:
                text = _clean_html(html, t)
                if text:
                    pages[t] = text
            bar.update(1)

    tasks = [asyncio.create_task(_fetch_one(t)) for t in titles]
    await asyncio.gather(*tasks)
    bar.close()

    # Sort alphabetically and write
    sorted_titles = sorted(pages.keys(), key=str.lower)
    body = "\n".join(pages[t] for t in sorted_titles)

    out = OUTPUT_DIR / filename
    out.write_text(body, encoding="utf-8")
    print(f"  Wrote {out} ({len(sorted_titles)} pages)")


async def main(limit: int | None = None) -> None:
    """Build all local database files."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    async with httpx.AsyncClient(
        timeout=30,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    ) as client:
        for filename, cats in CATEGORIES.items():
            print(f"Building {filename}...")
            try:
                await _build_file(client, filename, cats, limit, semaphore)
            except KeyboardInterrupt:
                print("\nInterrupted — writing partial results.")
                raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Build local PoE wiki database files.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max pages per category (for testing).",
    )
    args = parser.parse_args()

    try:
        asyncio.run(main(limit=args.limit))
    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(1)
