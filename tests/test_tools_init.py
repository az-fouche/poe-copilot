"""Tests for poe_agent/tools/__init__.py — 2 tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from poe_agent.tools import execute_tool


def test_execute_tool_dispatches_to_handler(settings):
    mock_handler = MagicMock(return_value={"prices": []})
    with patch.dict("poe_agent.tools._HANDLERS", {"get_currency_prices": mock_handler}):
        result = execute_tool("get_currency_prices", {"type": "Currency"}, settings)
    mock_handler.assert_called_once_with("get_currency_prices", {"type": "Currency"}, settings)
    assert result == {"prices": []}


def test_execute_tool_unknown(settings):
    result = execute_tool("fake_tool", {}, settings)
    assert result == {"error": "Unknown tool: fake_tool"}
