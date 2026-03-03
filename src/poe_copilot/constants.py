"""Centralized path and enum constants for the poe_copilot package."""

from enum import StrEnum
from pathlib import Path


class League(StrEnum):
    CHALLENGE = "challenge"
    STANDARD = "standard"


class GameMode(StrEnum):
    SOFTCORE_TRADE = "softcore_trade"
    HARDCORE_TRADE = "hardcore_trade"
    SSF = "ssf"
    HC_SSF = "hc_ssf"


class Backend(StrEnum):
    ANTHROPIC = "anthropic"
    OLLAMA = "ollama"


class Experience(StrEnum):
    NEWBIE = "newbie"
    CASUAL = "casual"
    INTERMEDIATE = "intermediate"
    VETERAN = "veteran"


# Package root: src/poe_copilot/
PACKAGE_DIR = Path(__file__).resolve().parent

# Asset directories
ASSETS_DIR = PACKAGE_DIR / "assets"
AGENTS_DIR = ASSETS_DIR / "agents"
LOADOUTS_DIR = AGENTS_DIR / "loadouts"
DATABASE_DIR = ASSETS_DIR / "database"

# Specific asset files
TIMELINE_FILE = ASSETS_DIR / "timeline.md"
REGISTRY_FILE = ASSETS_DIR / "registry.json"
IDENTITY_FILE = AGENTS_DIR / "identity.md"
PLAYER_CONTEXT_FILE = ASSETS_DIR / "player_context.md"

# A league becomes "the" league this many days before launch
PRE_LAUNCH_DAYS = 14

# Project root (repo level)
PROJECT_ROOT = PACKAGE_DIR.parent.parent
LOGS_DIR = PROJECT_ROOT / "logs"

# User settings
SETTINGS_DIR = Path.home() / ".poechat"
SETTINGS_FILE = SETTINGS_DIR / "settings.usr"
