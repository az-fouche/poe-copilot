"""Delegation tool schemas for the planner agent.

These look like normal tools to Claude but are intercepted by the orchestrator
to run sub-agent loops instead of executing Python handlers.
"""

DELEGATION_TOOLS = [
    {
        "name": "delegate_research",
        "description": (
            "Delegate a research task to the research specialist. "
            "The researcher has access to poe.ninja (prices, build meta), "
            "web search, and webpage reading. Returns a research report."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": (
                        "A clear, specific research task. Include what data you need "
                        "and why. Example: 'Look up the current build meta for league "
                        "starters — top ascendancies, most popular skills, and any "
                        "standout builds with high ladder representation.'"
                    ),
                },
            },
            "required": ["task"],
        },
    },
    {
        "name": "delegate_build",
        "description": (
            "Delegate a build composition task to the build specialist. "
            "The build agent researches and composes detailed build plans "
            "with gem links, gear progression, and leveling guides. "
            "Returns a structured build report."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": (
                        "What build to research/compose. Be specific about the skill, "
                        "ascendancy, or archetype. Example: 'Research and compose a "
                        "Lightning Arrow Deadeye build guide for league start.'"
                    ),
                },
                "context": {
                    "type": "string",
                    "description": (
                        "Optional prior research to build on. Pass findings from "
                        "earlier delegate_research calls so the build agent doesn't "
                        "repeat work."
                    ),
                },
            },
            "required": ["task"],
        },
    },
    {
        "name": "delegate_fact_check",
        "description": (
            "Send gathered research to the fact checker for verification. "
            "The fact checker looks for transfigured gem confusion, outdated info, "
            "unsupported claims, contradictions, and question relevance issues. "
            "Returns a list of issues and a verdict (CLEAN/NEEDS_FIX/CAUTION). "
            "Skip this for trivial or well-sourced data to save budget."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "research": {
                    "type": "string",
                    "description": "All gathered research and findings to verify.",
                },
                "original_question": {
                    "type": "string",
                    "description": "The player's original question for relevance checking.",
                },
            },
            "required": ["research", "original_question"],
        },
    },
]

DELEGATION_TOOL_NAMES = {tool["name"] for tool in DELEGATION_TOOLS}
