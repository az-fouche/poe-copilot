"""Tests for poe_copilot/onboarding.py — 4 tests."""

import json
from unittest.mock import patch

from poe_copilot.core.agent import NextStep
from poe_copilot.onboarding import load_settings, run_onboarding, save_settings

# ── load_settings ─────────────────────────────────────────────────────────


@patch("poe_copilot.onboarding.SETTINGS_FILE")
def test_load_settings_returns_dict(mock_file):
    data = {
        "api_key": "sk-test-key",
        "league": "Keepers",
        "mode": "ssf",
        "experience": "veteran",
    }
    mock_file.exists.return_value = True
    mock_file.read_text.return_value = json.dumps(data)
    result = load_settings()
    assert result == data


@patch("poe_copilot.onboarding.SETTINGS_FILE")
def test_load_settings_returns_none_when_missing(mock_file):
    mock_file.exists.return_value = False
    result = load_settings()
    assert result is None


# ── save_settings ─────────────────────────────────────────────────────────


@patch("poe_copilot.onboarding.SETTINGS_FILE")
@patch("poe_copilot.onboarding.SETTINGS_DIR")
def test_save_settings_creates_file(mock_dir, mock_file):
    data = {
        "api_key": "sk-test-key",
        "league": "Standard",
        "mode": "softcore_trade",
        "experience": "newbie",
    }
    save_settings(data)
    mock_dir.mkdir.assert_called_once_with(parents=True, exist_ok=True)
    mock_file.write_text.assert_called_once_with(json.dumps(data, indent=2))


# ── run_onboarding ────────────────────────────────────────────────────────


@patch("poe_copilot.onboarding.resolve_league", return_value="Mirage")
@patch("poe_copilot.onboarding.save_settings")
@patch("poe_copilot.onboarding.Prompt.ask")
@patch("poe_copilot.onboarding.Console")
def test_run_onboarding_collects_api_key(
    mock_console_cls, mock_ask, mock_save, mock_resolve
):
    # backend, api_key, league, mode, experience
    mock_ask.side_effect = ["1", "sk-ant-test-key", "1", "1", "3"]
    result = run_onboarding()
    assert result["backend"] == "anthropic"
    assert result["api_key"] == "sk-ant-test-key"
    assert result["league"] == "challenge"
    assert result["mode"] == "softcore_trade"
    assert result["experience"] == "intermediate"
    mock_save.assert_called_once_with(result)


@patch("poe_copilot.onboarding.resolve_league", return_value="Standard")
@patch("poe_copilot.onboarding.save_settings")
@patch("poe_copilot.onboarding.Prompt.ask")
@patch("poe_copilot.onboarding.Console")
def test_run_onboarding_preserves_existing_key(
    mock_console_cls, mock_ask, mock_save, mock_resolve
):
    existing = {
        "backend": "anthropic",
        "api_key": "sk-ant-existing",
        "league": "standard",
        "mode": "ssf",
        "experience": "veteran",
    }
    # backend, api_key (keep), league, mode, experience
    mock_ask.side_effect = ["1", "sk-ant-existing", "2", "1", "3"]
    result = run_onboarding(existing=existing)
    assert result["api_key"] == "sk-ant-existing"


# ── _status_label (orchestrator) ──────────────────────────────────────────


def test_status_label_target():
    from poe_copilot.core.orchestrator import Orchestrator

    # Test the _status_label method using a minimal instance
    ns = NextStep(type="call", input={"target": "analyst"})
    # Call the method directly — it doesn't need self state
    label = Orchestrator._status_label(None, ns)
    assert label == "Researching..."
