"""Web search and page-reading tool handlers."""

import os

import httpx
from bs4 import BeautifulSoup, Tag
from ddgs import DDGS

from poe_copilot.config import (
    HTTP_REQUEST_TIMEOUT,
    MAX_WEB_CONTENT_CHARS,
    MAX_WEB_INTRO_CHARS,
)

MAX_RESULTS = 8

# Tags whose content is noise rather than article text
_STRIP_TAGS = {
    "script",
    "style",
    "nav",
    "footer",
    "header",
    "aside",
    "noscript",
    "iframe",
    "svg",
    "form",
}

_HEADING_TAGS = {"h1", "h2", "h3", "h4"}

WEB_TOOLS = [
    {
        "name": "poe_web_search",
        "description": (
            "Search the web for Path of Exile information. Use for anything beyond "
            "prices: farming strategies, build guides, mechanic explanations, patch "
            "notes, crafting methods, community discussions. Returns top results with "
            "title, snippet, and URL."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Search query. Be specific — e.g. 'best div card farming "
                        "strategy 3.25' rather than 'div cards'. 'Path of Exile' is "
                        "automatically prepended if not present."
                    ),
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "read_webpage",
        "description": (
            "Fetch a webpage. Without a section parameter, returns the page outline "
            "(heading list + intro text). With a section parameter, returns the full "
            "content of that specific section. Use the outline first to find the right "
            "section, then fetch it."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The full URL of the page to read.",
                },
                "section": {
                    "type": "string",
                    "description": (
                        "Heading text to extract (e.g. 'Drop sources', 'Mechanics'). "
                        "Case-insensitive substring match. Omit to get the page outline."
                    ),
                },
            },
            "required": ["url"],
        },
    },
]


def _search(query: str) -> list[dict]:
    """Run a DuckDuckGo search and return top results."""
    # Keep results PoE-relevant
    if "path of exile" not in query.lower() and "poe" not in query.lower():
        query = f"Path of Exile {query}"

    try:
        # Suppress noisy "Impersonate 'chrome_xxx' does not exist" warnings
        # printed to stderr by the native primp library used internally by ddgs
        devnull = os.open(os.devnull, os.O_WRONLY)
        old_stderr = os.dup(2)
        os.dup2(devnull, 2)
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=MAX_RESULTS))
        finally:
            os.dup2(old_stderr, 2)
            os.close(old_stderr)
            os.close(devnull)
        return [
            {
                "title": r.get("title", ""),
                "snippet": r.get("body", ""),
                "url": r.get("href", ""),
            }
            for r in results
        ]
    except Exception as e:
        return [{"error": f"Search failed: {e}"}]


def _clean_soup(soup: BeautifulSoup) -> None:
    """Remove noisy elements from soup in-place."""
    for tag in soup.find_all(_STRIP_TAGS):
        tag.decompose()


def _extract_toc(soup: BeautifulSoup) -> list[dict]:
    """Walk h1-h4 tags and return a list of {"level": int, "text": str}."""
    toc = []
    for tag in soup.find_all(_HEADING_TAGS):
        level = int(tag.name[1])
        text = tag.get_text(strip=True)
        if text:
            toc.append({"level": level, "text": text})
    return toc


def _extract_section(soup: BeautifulSoup, section_query: str) -> str | None:
    """Extract text under the first heading matching *section_query*."""
    query_lower = section_query.lower()

    # Find the first heading whose text contains the query
    target = None
    for tag in soup.find_all(_HEADING_TAGS):
        if query_lower in tag.get_text(strip=True).lower():
            target = tag
            break

    if target is None:
        return None

    target_level = int(target.name[1])
    parts = [target.get_text(strip=True)]

    # Collect everything after target until a same-or-higher-level heading
    for sibling in target.find_next_siblings():
        if isinstance(sibling, Tag) and sibling.name in _HEADING_TAGS:
            sibling_level = int(sibling.name[1])
            if sibling_level <= target_level:
                break
            # Sub-heading within the section — include it
            parts.append(
                f"\n{'#' * sibling_level} {sibling.get_text(strip=True)}"
            )
            continue
        text = (
            sibling.get_text(separator="\n", strip=True)
            if isinstance(sibling, Tag)
            else str(sibling).strip()
        )
        if text:
            parts.append(text)

    content = "\n".join(parts)
    if len(content) > MAX_WEB_CONTENT_CHARS:
        content = content[:MAX_WEB_CONTENT_CHARS] + "\n\n[... content truncated]"
    return content


def _get_body_text(soup: BeautifulSoup) -> str:
    """Get full body text, collapsed whitespace."""
    text = soup.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def _read_page(url: str, section: str | None = None) -> dict:
    """Fetch a webpage and return its outline or a targeted section."""
    try:
        with httpx.Client(
            timeout=HTTP_REQUEST_TIMEOUT,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            },
        ) as client:
            resp = client.get(url)
            resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        title = (
            soup.title.string.strip() if soup.title and soup.title.string else ""
        )
        _clean_soup(soup)

        if section:
            # Targeted section mode
            content = _extract_section(soup, section)
            if content is None:
                # Fallback: return available sections so the agent can retry
                toc = _extract_toc(soup)
                section_names = [h["text"] for h in toc]
                return {
                    "url": url,
                    "title": title,
                    "error": f"Section '{section}' not found.",
                    "available_sections": section_names,
                }
            return {
                "url": url,
                "title": title,
                "section": section,
                "content": content,
            }
        else:
            # Overview mode: TOC + intro
            toc = _extract_toc(soup)
            section_names = [h["text"] for h in toc]

            body = _get_body_text(soup)
            intro = body[:MAX_WEB_INTRO_CHARS]
            if len(body) > MAX_WEB_INTRO_CHARS:
                intro += (
                    "\n\n[... use section parameter to read specific sections]"
                )

            return {
                "url": url,
                "title": title,
                "sections": section_names,
                "intro": intro,
            }

    except httpx.HTTPStatusError as e:
        return {"url": url, "error": f"HTTP {e.response.status_code}"}
    except httpx.RequestError as e:
        return {"url": url, "error": f"Request failed: {e}"}


def handle_web_tool(name: str, params: dict, settings: dict) -> dict:
    """Dispatch a web tool call and return search results or page content.

    Parameters
    ----------
    name : str
        Tool name — ``"poe_web_search"`` or ``"read_webpage"``.
    params : dict
        Tool-specific parameters from the API request.
    settings : dict
        User settings (currently unused, reserved for future use).

    Returns
    -------
    dict
        Search results or page content.  Contains an ``"error"`` key
        on failure.
    """
    if name == "poe_web_search":
        query = params.get("query", "")
        if not query:
            return {"error": "Missing required parameter: query"}
        results = _search(query)
        return {"query": query, "results": results}

    elif name == "read_webpage":
        url = params.get("url", "")
        if not url:
            return {"error": "Missing required parameter: url"}
        section = params.get("section")
        return _read_page(url, section=section)

    return {"error": f"Unknown web tool: {name}"}
