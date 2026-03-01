"""Shared fixtures and mock factories for poe-copilot tests."""

from unittest.mock import MagicMock

import pytest

from poe_copilot.backends import ContentBlock, ToolUseBlock

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
# LLMBackend mock helpers
# ---------------------------------------------------------------------------


def make_text_response(text: str) -> list[ContentBlock]:
    """Build a content block list with a single text block."""
    return [text]


def make_tool_response(tool_calls: list[dict]) -> list[ContentBlock]:
    """Build a content block list with ToolUseBlock items.

    Each dict should have keys: id, name, input.
    """
    return [
        ToolUseBlock(id=tc["id"], name=tc["name"], input=tc["input"])
        for tc in tool_calls
    ]


def make_mixed_response(text: str, tool_calls: list[dict]) -> list[ContentBlock]:
    """Build a content block list with both text and tool_use blocks."""
    blocks: list[ContentBlock] = [text]
    blocks.extend(
        ToolUseBlock(id=tc["id"], name=tc["name"], input=tc["input"])
        for tc in tool_calls
    )
    return blocks


@pytest.fixture
def mock_backend():
    def _factory(responses=None, side_effect=None):
        backend = MagicMock()
        if side_effect is not None:
            backend.complete.side_effect = side_effect
        elif responses is not None:
            backend.complete.side_effect = responses
        else:
            backend.complete.return_value = make_text_response("ok")
        return backend

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
