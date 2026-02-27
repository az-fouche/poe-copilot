from __future__ import annotations

import logging
import httpx
from bs4 import BeautifulSoup
from ddgs import DDGS

MAX_CONTENT_CHARS = 6000
MAX_RESULTS = 8

# Tags whose content is noise rather than article text
_STRIP_TAGS = {
    "script", "style", "nav", "footer", "header", "aside",
    "noscript", "iframe", "svg", "form",
}

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
            "Fetch and read the text content of a webpage. Use to get full details "
            "from a promising search result. Don't read every result — pick the 1-2 "
            "most relevant. Content is truncated to avoid blowing context."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The full URL of the page to read.",
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
        # from curl_cffi used internally by ddgs
        logging.getLogger("curl_cffi").setLevel(logging.ERROR)
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=MAX_RESULTS))
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


def _extract_text(html: str) -> tuple[str, str]:
    """Extract readable text from HTML. Returns (title, body_text)."""
    soup = BeautifulSoup(html, "html.parser")

    title = soup.title.string.strip() if soup.title and soup.title.string else ""

    # Remove noisy elements
    for tag in soup.find_all(_STRIP_TAGS):
        tag.decompose()

    # Get text, collapse whitespace
    text = soup.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines()]
    text = "\n".join(line for line in lines if line)

    if len(text) > MAX_CONTENT_CHARS:
        text = text[:MAX_CONTENT_CHARS] + "\n\n[... content truncated]"

    return title, text


def _read_page(url: str) -> dict:
    """Fetch a webpage and return its text content."""
    try:
        with httpx.Client(
            timeout=15,
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

        title, content = _extract_text(resp.text)
        return {"url": url, "title": title, "content": content}

    except httpx.HTTPStatusError as e:
        return {"url": url, "error": f"HTTP {e.response.status_code}"}
    except httpx.RequestError as e:
        return {"url": url, "error": f"Request failed: {e}"}


def handle_web_tool(name: str, params: dict, settings: dict) -> dict:
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
        return _read_page(url)

    return {"error": f"Unknown web tool: {name}"}
