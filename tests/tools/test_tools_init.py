"""Tests for poe_copilot/tools/__init__.py."""

from poe_copilot.tools import _HANDLERS, TOOL_DEFINITIONS


def test_handlers_cover_all_tool_definitions():
    """Every tool in TOOL_DEFINITIONS has a handler registered."""
    tool_names = {t["name"] for t in TOOL_DEFINITIONS}
    assert tool_names == set(_HANDLERS.keys())
