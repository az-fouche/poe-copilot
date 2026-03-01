"""Tests for poe_copilot/tools/poe_ninja.py — 18 tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx

from poe_copilot.tools.poe_ninja import (
    _extract_sparkline,
    _league_slug,
    handle_poe_ninja_tool,
)


# ── _league_slug ──────────────────────────────────────────────────────────


def test_league_slug_multi_word():
    assert _league_slug("Settlers of Kalguur") == "settlers-of-kalguur"


def test_league_slug_single_word():
    assert _league_slug("Standard") == "standard"


# ── _extract_sparkline ────────────────────────────────────────────────────


def test_sparkline_none_input():
    assert _extract_sparkline(None) is None


def test_sparkline_empty_dict():
    assert _extract_sparkline({}) is None


def test_sparkline_only_total_change():
    result = _extract_sparkline({"totalChange": -5.256})
    assert result == {"total_change_pct": -5.26}


def test_sparkline_only_data_points():
    result = _extract_sparkline({"data": [1.005, None, 3.0]})
    assert result == {"sparkline": [1.0, 0.0, 3.0]}


def test_sparkline_full():
    result = _extract_sparkline({"totalChange": 2.5, "data": [1.0, 2.0]})
    assert result == {"total_change_pct": 2.5, "sparkline": [1.0, 2.0]}


def test_sparkline_zero_change_not_none():
    result = _extract_sparkline({"totalChange": 0})
    assert result == {"total_change_pct": 0}


# ── handle_poe_ninja_tool — currency ──────────────────────────────────────


@patch("poe_copilot.tools.poe_ninja._fetch")
def test_currency_prices_basic(mock_fetch, settings):
    mock_fetch.return_value = {
        "lines": [
            {"currencyTypeName": "Divine Orb", "chaosEquivalent": 150.0},
            {"currencyTypeName": "Exalted Orb", "chaosEquivalent": 14.5},
        ]
    }
    result = handle_poe_ninja_tool(
        "get_currency_prices", {"type": "Currency"}, settings
    )
    assert result == {
        "league": "Keepers",
        "type": "Currency",
        "count": 2,
        "prices": [
            {"name": "Divine Orb", "chaos_equivalent": 150.0},
            {"name": "Exalted Orb", "chaos_equivalent": 14.5},
        ],
    }


@patch("poe_copilot.tools.poe_ninja._fetch")
def test_currency_prices_league_fallback_to_settings(mock_fetch, settings):
    mock_fetch.return_value = {"lines": []}
    handle_poe_ninja_tool("get_currency_prices", {"type": "Currency"}, settings)
    mock_fetch.assert_called_once_with(
        "currencyoverview", {"league": "Keepers", "type": "Currency"}
    )


@patch("poe_copilot.tools.poe_ninja._fetch")
def test_currency_prices_empty_lines(mock_fetch, settings):
    mock_fetch.return_value = {"lines": []}
    result = handle_poe_ninja_tool(
        "get_currency_prices", {"type": "Currency"}, settings
    )
    assert result == {
        "league": "Keepers",
        "type": "Currency",
        "count": 0,
        "prices": [],
    }


@patch("poe_copilot.tools.poe_ninja._fetch")
def test_currency_prices_capped_at_50(mock_fetch, settings):
    mock_fetch.return_value = {
        "lines": [
            {"currencyTypeName": f"Orb{i}", "chaosEquivalent": float(i)}
            for i in range(60)
        ]
    }
    result = handle_poe_ninja_tool(
        "get_currency_prices", {"type": "Currency"}, settings
    )
    assert result["count"] == 50
    assert len(result["prices"]) == 50


# ── handle_poe_ninja_tool — items ─────────────────────────────────────────


@patch("poe_copilot.tools.poe_ninja._fetch")
def test_item_prices_with_name_filter(mock_fetch, settings):
    mock_fetch.return_value = {
        "lines": [
            {"name": "Headhunter", "chaosValue": 8500.0, "divineValue": 56.67},
            {"name": "Mageblood", "chaosValue": 45000.0, "divineValue": 300.0},
            {"name": "Headcracker", "chaosValue": 1.0, "divineValue": 0.01},
        ]
    }
    result = handle_poe_ninja_tool(
        "get_item_prices",
        {"type": "UniqueArmour", "name_filter": "head"},
        settings,
    )
    assert result["count"] == 2
    names = [i["name"] for i in result["items"]]
    assert "Headhunter" in names
    assert "Headcracker" in names
    assert "Mageblood" not in names


@patch("poe_copilot.tools.poe_ninja._fetch")
def test_item_prices_gem_fields(mock_fetch, settings):
    mock_fetch.return_value = {
        "lines": [
            {
                "name": "Vaal Grace",
                "chaosValue": 50.0,
                "divineValue": 0.33,
                "gemLevel": 21,
                "gemQuality": 23,
            }
        ]
    }
    result = handle_poe_ninja_tool(
        "get_item_prices", {"type": "SkillGem"}, settings
    )
    item = result["items"][0]
    assert item["gem_level"] == 21
    assert item["gem_quality"] == 23


@patch("poe_copilot.tools.poe_ninja._fetch")
def test_item_prices_optional_fields_absent(mock_fetch, settings):
    mock_fetch.return_value = {
        "lines": [
            {"name": "Scarab of Speed", "chaosValue": 5.0, "divineValue": 0.03}
        ]
    }
    result = handle_poe_ninja_tool(
        "get_item_prices", {"type": "Scarab"}, settings
    )
    item = result["items"][0]
    assert set(item.keys()) == {"name", "chaos_value", "divine_value"}


# ── handle_poe_ninja_tool — build meta ────────────────────────────────────


@patch("poe_copilot.tools.poe_ninja._fetch")
def test_build_meta_sorted_by_count(
    mock_fetch, settings, poe_ninja_build_payload
):
    mock_fetch.return_value = poe_ninja_build_payload
    result = handle_poe_ninja_tool("get_build_meta", {}, settings)
    counts = [a["count"] for a in result["ascendancies"]]
    assert counts == sorted(counts, reverse=True)


@patch("poe_copilot.tools.poe_ninja._fetch")
def test_build_meta_class_filter(mock_fetch, settings, poe_ninja_build_payload):
    mock_fetch.return_value = poe_ninja_build_payload
    result = handle_poe_ninja_tool(
        "get_build_meta", {"class_filter": "necromancer"}, settings
    )
    assert result["filtered_by"] == "necromancer"
    for skill in result["top_skills"]:
        assert skill["name"] == "Summon Raging Spirit"


# ── error handling ────────────────────────────────────────────────────────


@patch("poe_copilot.tools.poe_ninja._fetch")
def test_http_404_error_with_hint(mock_fetch, settings):
    resp = MagicMock()
    resp.status_code = 404
    mock_fetch.side_effect = httpx.HTTPStatusError(
        "Not Found", request=MagicMock(), response=resp
    )
    result = handle_poe_ninja_tool(
        "get_currency_prices", {"type": "Currency"}, settings
    )
    assert result["error"] == "poe.ninja returned HTTP 404"
    assert result["hint"] == "Check that the league name is correct."
