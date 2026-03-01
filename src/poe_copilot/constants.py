"""Centralized path constants for the poe_copilot package."""

from pathlib import Path

# Package root: src/poe_copilot/
PACKAGE_DIR = Path(__file__).resolve().parent

# Asset directories
ASSETS_DIR = PACKAGE_DIR / "assets"
AGENTS_DIR = ASSETS_DIR / "agents"

# Specific asset files
TIMELINE_FILE = ASSETS_DIR / "timeline.md"
REGISTRY_FILE = ASSETS_DIR / "registry.json"

# Project root (repo level)
PROJECT_ROOT = PACKAGE_DIR.parent.parent
LOGS_DIR = PROJECT_ROOT / "logs"

# User settings
SETTINGS_DIR = Path.home() / ".poechat"
SETTINGS_FILE = SETTINGS_DIR / "settings.usr"
