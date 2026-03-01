"""Shared fixtures and mock factories for poe-copilot tests."""

from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Settings fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def settings() -> dict:
    return {
        "league": "Keepers",
        "mode": "softcore_trade",
        "experience": "intermediate",
    }


# ---------------------------------------------------------------------------
# Anthropic mock helpers
# ---------------------------------------------------------------------------


@dataclass
class _TextBlock:
    type: str
    text: str


@dataclass
class _ToolUseBlock:
    type: str
    id: str
    name: str
    input: dict


@dataclass
class _Message:
    content: list[Any]
    stop_reason: str = "end_turn"


def make_text_response(text: str) -> _Message:
    """Build a mock Anthropic Message with a single TextBlock."""
    return _Message(content=[_TextBlock(type="text", text=text)])


def make_tool_response(tool_calls: list[dict]) -> _Message:
    """Build a mock Anthropic Message with ToolUseBlock items.

    Each dict should have keys: id, name, input.
    """
    blocks = [
        _ToolUseBlock(
            type="tool_use", id=tc["id"], name=tc["name"], input=tc["input"]
        )
        for tc in tool_calls
    ]
    return _Message(content=blocks, stop_reason="tool_use")


def make_mixed_response(text: str, tool_calls: list[dict]) -> _Message:
    """Build a mock Anthropic Message with both text and tool_use blocks."""
    blocks: list[Any] = [_TextBlock(type="text", text=text)]
    blocks.extend(
        _ToolUseBlock(
            type="tool_use", id=tc["id"], name=tc["name"], input=tc["input"]
        )
        for tc in tool_calls
    )
    return _Message(content=blocks, stop_reason="tool_use")


@pytest.fixture
def mock_anthropic_client():
    """Factory that returns a mock anthropic.Anthropic whose .messages.create()
    returns configurable responses (pass a list to side_effect for sequences)."""

    def _factory(responses=None, side_effect=None):
        client = MagicMock()
        if side_effect is not None:
            client.messages.create.side_effect = side_effect
        elif responses is not None:
            client.messages.create.side_effect = responses
        else:
            client.messages.create.return_value = make_text_response("ok")
        return client

    return _factory


# ---------------------------------------------------------------------------
# poe.ninja realistic payloads
# ---------------------------------------------------------------------------


@pytest.fixture
def poe_ninja_currency_payload() -> dict:
    return {
        "lines": [
            {
                "currencyTypeName": "Divine Orb",
                "chaosEquivalent": 150.0,
                "receiveSparkLine": {
                    "totalChange": 2.5,
                    "data": [140.0, 145.0, 150.0],
                },
            },
            {
                "currencyTypeName": "Exalted Orb",
                "chaosEquivalent": 14.5,
                "receiveSparkLine": {
                    "totalChange": -1.2,
                    "data": [15.0, 14.8, 14.5],
                },
            },
        ]
    }


@pytest.fixture
def poe_ninja_item_payload() -> dict:
    return {
        "lines": [
            {
                "name": "Headhunter",
                "chaosValue": 8500.0,
                "divineValue": 56.67,
                "links": 0,
                "variant": None,
            },
            {
                "name": "Mageblood",
                "chaosValue": 45000.0,
                "divineValue": 300.0,
                "links": 0,
                "variant": None,
            },
            {
                "name": "Tabula Rasa",
                "chaosValue": 10.0,
                "divineValue": 0.07,
                "links": 6,
            },
        ]
    }


@pytest.fixture
def poe_ninja_build_payload() -> dict:
    return {
        "classes": [
            {"name": "Necromancer", "count": 500, "percentage": 12.5},
            {"name": "Juggernaut", "count": 300, "percentage": 7.5},
            {"name": "Deadeye", "count": 700, "percentage": 17.5},
        ],
        "activeSkills": [
            {
                "name": "Summon Raging Spirit",
                "count": 200,
                "percentage": 5.0,
                "classes": [{"name": "Necromancer"}],
            },
            {
                "name": "Boneshatter",
                "count": 150,
                "percentage": 3.75,
                "classes": [{"name": "Juggernaut"}],
            },
            {
                "name": "Lightning Arrow",
                "count": 300,
                "percentage": 7.5,
                "classes": [{"name": "Deadeye"}],
            },
        ],
        "uniqueItems": [
            {"name": "Headhunter", "count": 100, "percentage": 2.5},
            {"name": "Mageblood", "count": 80, "percentage": 2.0},
        ],
        "keystones": [
            {"name": "Resolute Technique", "count": 120, "percentage": 3.0},
            {"name": "Chaos Inoculation", "count": 90, "percentage": 2.25},
        ],
    }
