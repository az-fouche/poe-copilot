"""Tests for poe_copilot/tools/web.py — 16 tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
from bs4 import BeautifulSoup

from poe_copilot.tools.web import (
    _clean_soup,
    _extract_section,
    _extract_toc,
    _read_page,
    _search,
    handle_web_tool,
)


# ── _search ───────────────────────────────────────────────────────────────


@patch("poe_copilot.tools.web.os.close")
@patch("poe_copilot.tools.web.os.dup2")
@patch("poe_copilot.tools.web.os.dup")
@patch("poe_copilot.tools.web.os.open", return_value=99)
@patch("poe_copilot.tools.web.DDGS")
def test_search_prepends_poe(
    mock_ddgs, mock_open, mock_dup, mock_dup2, mock_close
):
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=ctx)
    ctx.__exit__ = MagicMock(return_value=False)
    ctx.text.return_value = []
    mock_ddgs.return_value = ctx
    mock_dup.return_value = 5

    _search("divine orb price")
    ctx.text.assert_called_once()
    query_arg = ctx.text.call_args[0][0]
    assert query_arg.startswith("Path of Exile")


@patch("poe_copilot.tools.web.os.close")
@patch("poe_copilot.tools.web.os.dup2")
@patch("poe_copilot.tools.web.os.dup")
@patch("poe_copilot.tools.web.os.open", return_value=99)
@patch("poe_copilot.tools.web.DDGS")
def test_search_no_prepend_if_poe_present(
    mock_ddgs, mock_open, mock_dup, mock_dup2, mock_close
):
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=ctx)
    ctx.__exit__ = MagicMock(return_value=False)
    ctx.text.return_value = []
    mock_ddgs.return_value = ctx
    mock_dup.return_value = 5

    _search("poe ninja divine")
    query_arg = ctx.text.call_args[0][0]
    assert query_arg == "poe ninja divine"


@patch("poe_copilot.tools.web.os.close")
@patch("poe_copilot.tools.web.os.dup2")
@patch("poe_copilot.tools.web.os.dup")
@patch("poe_copilot.tools.web.os.open", return_value=99)
@patch("poe_copilot.tools.web.DDGS")
def test_search_returns_formatted_results(
    mock_ddgs, mock_open, mock_dup, mock_dup2, mock_close
):
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=ctx)
    ctx.__exit__ = MagicMock(return_value=False)
    ctx.text.return_value = [{"title": "T", "body": "S", "href": "U"}]
    mock_ddgs.return_value = ctx
    mock_dup.return_value = 5

    results = _search("poe test")
    assert results == [{"title": "T", "snippet": "S", "url": "U"}]


@patch("poe_copilot.tools.web.os.close")
@patch("poe_copilot.tools.web.os.dup2")
@patch("poe_copilot.tools.web.os.dup")
@patch("poe_copilot.tools.web.os.open", return_value=99)
@patch("poe_copilot.tools.web.DDGS")
def test_search_exception_returns_error(
    mock_ddgs, mock_open, mock_dup, mock_dup2, mock_close
):
    mock_ddgs.side_effect = RuntimeError("timeout")

    results = _search("poe test")
    assert len(results) == 1
    assert "Search failed: timeout" in results[0]["error"]


# ── _clean_soup ───────────────────────────────────────────────────────────


def test_clean_soup_strips_noise():
    html = "<html><nav>X</nav><p>keep</p><script>Y</script></html>"
    soup = BeautifulSoup(html, "html.parser")
    _clean_soup(soup)
    assert soup.get_text(strip=True) == "keep"


# ── _extract_toc ──────────────────────────────────────────────────────────


def test_extract_toc_h1_through_h4():
    html = "<h1>A</h1><h2>B</h2><h3>C</h3><h4>D</h4><h5>E</h5>"
    soup = BeautifulSoup(html, "html.parser")
    toc = _extract_toc(soup)
    assert toc == [
        {"level": 1, "text": "A"},
        {"level": 2, "text": "B"},
        {"level": 3, "text": "C"},
        {"level": 4, "text": "D"},
    ]


def test_extract_toc_skips_empty_headings():
    html = "<h2></h2><h2>Real</h2>"
    soup = BeautifulSoup(html, "html.parser")
    toc = _extract_toc(soup)
    assert toc == [{"level": 2, "text": "Real"}]


# ── _extract_section ─────────────────────────────────────────────────────


def test_extract_section_basic():
    html = "<h2>Mechanics</h2><p>content here</p><h2>Next</h2>"
    soup = BeautifulSoup(html, "html.parser")
    result = _extract_section(soup, "Mechanics")
    assert result == "Mechanics\ncontent here"


def test_extract_section_case_insensitive():
    html = "<h2>Mechanics</h2><p>stuff</p><h2>End</h2>"
    soup = BeautifulSoup(html, "html.parser")
    result = _extract_section(soup, "mech")
    assert result is not None
    assert "stuff" in result


def test_extract_section_not_found():
    html = "<h2>Intro</h2><p>text</p>"
    soup = BeautifulSoup(html, "html.parser")
    result = _extract_section(soup, "nonexistent")
    assert result is None


def test_extract_section_truncates_at_6000():
    long_text = "x" * 7000
    html = f"<h2>Big</h2><p>{long_text}</p><h2>End</h2>"
    soup = BeautifulSoup(html, "html.parser")
    result = _extract_section(soup, "Big")
    assert result.endswith("\n\n[... content truncated]")
    assert len(result) == 6000 + len("\n\n[... content truncated]")


def test_extract_section_includes_subheadings():
    html = "<h2>Main</h2><p>text</p><h3>Sub</h3><p>more</p><h2>End</h2>"
    soup = BeautifulSoup(html, "html.parser")
    result = _extract_section(soup, "Main")
    assert "\n### Sub" in result


# ── _read_page ────────────────────────────────────────────────────────────


@patch("poe_copilot.tools.web.httpx.Client")
def test_read_page_overview_mode(mock_client_cls):
    html = "<html><head><title>Test Page</title></head><body><h2>Intro</h2><p>Hello world</p></body></html>"
    mock_resp = MagicMock()
    mock_resp.text = html
    mock_resp.raise_for_status = MagicMock()
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=ctx)
    ctx.__exit__ = MagicMock(return_value=False)
    ctx.get.return_value = mock_resp
    mock_client_cls.return_value = ctx

    result = _read_page("http://example.com")
    assert result["url"] == "http://example.com"
    assert result["title"] == "Test Page"
    assert "sections" in result
    assert "intro" in result


@patch("poe_copilot.tools.web.httpx.Client")
def test_read_page_section_not_found(mock_client_cls):
    html = "<html><head><title>Page</title></head><body><h2>Real</h2><p>data</p></body></html>"
    mock_resp = MagicMock()
    mock_resp.text = html
    mock_resp.raise_for_status = MagicMock()
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=ctx)
    ctx.__exit__ = MagicMock(return_value=False)
    ctx.get.return_value = mock_resp
    mock_client_cls.return_value = ctx

    result = _read_page("http://example.com", section="Ghost")
    assert result["error"] == "Section 'Ghost' not found."
    assert "available_sections" in result


@patch("poe_copilot.tools.web.httpx.Client")
def test_read_page_http_error(mock_client_cls):
    resp = MagicMock()
    resp.status_code = 403
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=ctx)
    ctx.__exit__ = MagicMock(return_value=False)
    ctx.get.side_effect = httpx.HTTPStatusError(
        "Forbidden", request=MagicMock(), response=resp
    )
    mock_client_cls.return_value = ctx

    result = _read_page("http://x.com")
    assert result == {"url": "http://x.com", "error": "HTTP 403"}


# ── handle_web_tool ───────────────────────────────────────────────────────


def test_handle_web_tool_missing_query(settings):
    result = handle_web_tool("poe_web_search", {}, settings)
    assert result == {"error": "Missing required parameter: query"}
