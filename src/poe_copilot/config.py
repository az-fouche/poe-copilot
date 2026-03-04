"""Configuration constants for the poe_copilot package.

This module centralizes magic numbers that were previously scattered
throughout the codebase. These values control API limits, timeouts,
truncation lengths, and other tunable parameters.
"""

# API Configuration
DEFAULT_MAX_API_CALLS = 25
DEFAULT_MAX_TOKENS = 4096
HTTP_REQUEST_TIMEOUT = 15
POE_NINJA_TIMEOUT = 10

# Content Length Limits
MAX_WEB_CONTENT_CHARS = 6000
MAX_WEB_INTRO_CHARS = 2000
MAX_LOG_PREVIEW_CHARS = 500
MAX_DELEGATION_RESULT_CHARS = 2000
MAX_PARTIAL_RESULT_CHARS = 2000

# Message History Limits
ASSISTANT_MESSAGE_CHAR_LIMIT = 1500
USER_MESSAGE_CHAR_LIMIT = 300
MAX_RESEARCH_ITEMS_FOR_ANSWER = 20

# UI Display Truncation
TRUNCATE_SECTION_CHARS = 25
TRUNCATE_SHORT_URL_CHARS = 30
TRUNCATE_LONG_URL_CHARS = 45
TRUNCATE_QUERY_CHARS = 45
TRUNCATE_NAME_FILTER_CHARS = 30
TRUNCATE_ITEM_TYPE_CHARS = 30

# Time Display
SECONDS_PER_MINUTE = 60

# poe.ninja API Limits
POE_NINJA_MAX_RESULTS = 50
POE_NINJA_MAX_BUILD_META_RESULTS = 15
