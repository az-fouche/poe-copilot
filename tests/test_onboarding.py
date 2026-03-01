"""Tests for poe_agent/onboarding.py — 4 tests."""

from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

import pytest

from poe_agent.onboarding import load_settings, save_settings
from poe_agent.orchestrator import _STATUS_LABELS
from poe_agent.agent import NextStep


# ── load_settings ─────────────────────────────────────────────────────────

@patch("poe_agent.onboarding.SETTINGS_FILE")
def test_load_settings_returns_dict(mock_file):
    data = {"league": "Keepers", "mode": "ssf", "experience": "veteran"}
    mock_file.exists.return_value = True
    mock_file.read_text.return_value = json.dumps(data)
    result = load_settings()
    assert result == data


@patch("poe_agent.onboarding.SETTINGS_FILE")
def test_load_settings_returns_none_when_missing(mock_file):
    mock_file.exists.return_value = False
    result = load_settings()
    assert result is None


# ── save_settings ─────────────────────────────────────────────────────────

@patch("poe_agent.onboarding.SETTINGS_FILE")
@patch("poe_agent.onboarding.SETTINGS_DIR")
def test_save_settings_creates_file(mock_dir, mock_file):
    data = {"league": "Standard", "mode": "softcore_trade", "experience": "newbie"}
    save_settings(data)
    mock_dir.mkdir.assert_called_once_with(parents=True, exist_ok=True)
    mock_file.write_text.assert_called_once_with(json.dumps(data, indent=2))


# ── _status_label (orchestrator) ──────────────────────────────────────────

def test_status_label_target():
    from poe_agent.orchestrator import Orchestrator
    # Test the _status_label method using a minimal instance
    ns = NextStep(type="call", input={"target": "researcher"})
    # Call the method directly — it doesn't need self state
    label = Orchestrator._status_label(None, ns)
    assert label == "Researching..."
