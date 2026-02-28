from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import anthropic

logger = logging.getLogger(__name__)

HAIKU_MODEL = "claude-haiku-4-5-20251001"

_PATCH_NOTES_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "patch_notes"


def _available_patches() -> list[str]:
    return [f.stem for f in sorted(_PATCH_NOTES_DIR.glob("*.md"))]


@dataclass
class ClarifyingQuestion:
    question: str
    options: list[str]


@dataclass
class RoutingDecision:
    action: str  # "clarify" or "answer"
    clarifying_questions: list[ClarifyingQuestion] = field(default_factory=list)
    complexity: str = "complex"  # "simple" or "complex"
    required_research: list[dict] = field(default_factory=list)
    enriched_query: str = ""
    response_guidance: str = ""


_ROUTER_PROMPT = """\
You are a request router for a Path of Exile assistant. Your job is to classify \
the user's question and decide what research is needed BEFORE the answering model runs.

## Player Profile
- League: {league}
- Mode: {mode}
- Experience: {experience}

## Available Patch Notes
{patches}

## Available Tools
- load_patch_notes: Load curated patch notes (params: {{"patch": "<id>"}})
- poe_web_search: Search the web for PoE info (params: {{"query": "<search query>"}})
- get_currency_prices: Currency exchange rates from poe.ninja (params: {{"type": "Currency"|"Fragment"}})
- get_item_prices: Item prices from poe.ninja (params: {{"type": "<category>", "name_filter": "<optional>"}})

## Classification Rules

| Question type | Complexity | Required research |
|---|---|---|
| Build recommendation / "league starter?" | complex | latest patch_notes + web_search for guides |
| "Is X good/viable?" | complex | latest patch_notes + web_search |
| Price check / "how much is X?" | simple | poe.ninja tool (get_currency_prices or get_item_prices) |
| Mechanic explanation / "how does X work?" | simple | web_search (site:poewiki.net) |
| Farming strategy | complex | web_search + latest patch_notes + poe.ninja if relevant |
| Atlas / endgame strategy | complex | patch_notes + web_search |
| Simple factual / wiki lookup | simple | web_search (site:poewiki.net) |
| Greeting / chitchat / thanks | simple | none |
| Vague / missing info needed | clarify | ask 1-2 targeted questions |

## Instructions

1. Read the user message and recent conversation context.
2. If critical info is missing (e.g., "help with my build" but no details), return action "clarify" with 1-2 questions. Each question should have 3-4 selectable options plus implied "Other".
3. If you have enough info, return action "answer" with:
   - complexity: "simple" or "complex"
   - required_research: list of tool calls to execute BEFORE the answering model
   - enriched_query: rewrite the user's question with full context (player profile, conversation history)
   - response_guidance: brief instruction for the answering model on how to structure the answer

For required_research, formulate good search queries:
- Build questions: search for "[skill/archetype] build guide [current patch] [league name]"
- Mechanic questions: search for "site:poewiki.net [mechanic]"
- Strategy questions: search for "[strategy] [current league] reddit"

## Output Format

Return ONLY valid JSON, no markdown fences, no extra text:
{{"action": "clarify"|"answer", "clarifying_questions": [...], "complexity": "simple"|"complex", "required_research": [...], "enriched_query": "...", "response_guidance": "..."}}

For clarify:
{{"action": "clarify", "clarifying_questions": [{{"question": "...", "options": ["A", "B", "C"]}}]}}

For answer:
{{"action": "answer", "complexity": "simple", "required_research": [{{"tool": "tool_name", "params": {{...}}}}], "enriched_query": "...", "response_guidance": "..."}}
"""


class Router:
    def __init__(self, settings: dict, client: anthropic.Anthropic):
        self.settings = settings
        self.client = client
        self._system_prompt = self._build_prompt()

    def _build_prompt(self) -> str:
        patches = _available_patches()
        patch_list = ", ".join(f"`{p}`" for p in patches) if patches else "(none available)"
        return _ROUTER_PROMPT.format(
            league=self.settings.get("league", "Standard"),
            mode=self.settings.get("mode", "softcore_trade"),
            experience=self.settings.get("experience", "intermediate"),
            patches=patch_list,
        )

    def route(
        self,
        user_message: str,
        recent_messages: list[dict],
    ) -> RoutingDecision:
        # Build a compact context from recent conversation
        context_parts = []
        for msg in recent_messages[-6:]:  # last 3 exchanges (user+assistant pairs)
            role = msg.get("role", "")
            content = msg.get("content", "")
            if isinstance(content, list):
                # Extract text from content blocks
                text_parts = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text_parts.append(block["text"])
                    elif hasattr(block, "type") and block.type == "text":
                        text_parts.append(block.text)
                content = " ".join(text_parts)
            if content and isinstance(content, str):
                context_parts.append(f"{role}: {content[:300]}")

        context_str = "\n".join(context_parts) if context_parts else "(new conversation)"

        messages = [
            {
                "role": "user",
                "content": (
                    f"Recent conversation:\n{context_str}\n\n"
                    f"Current user message: {user_message}"
                ),
            }
        ]

        try:
            response = self.client.messages.create(
                model=HAIKU_MODEL,
                max_tokens=1024,
                system=self._system_prompt,
                messages=messages,
            )

            text = response.content[0].text.strip()
            # Strip markdown fences if present
            if text.startswith("```"):
                text = text.split("\n", 1)[1] if "\n" in text else text[3:]
                if text.endswith("```"):
                    text = text[:-3]
                text = text.strip()

            data = json.loads(text)
            return self._parse_decision(data)

        except (json.JSONDecodeError, KeyError, IndexError) as e:
            logger.warning("Router parse error: %s — falling back to complex/full research", e)
            return self.fallback_decision(user_message)
        except anthropic.APIError as e:
            logger.warning("Router API error: %s — falling back to complex/full research", e)
            return self.fallback_decision(user_message)

    def _parse_decision(self, data: dict) -> RoutingDecision:
        action = data.get("action", "answer")

        if action == "clarify":
            questions = []
            for q in data.get("clarifying_questions", []):
                questions.append(
                    ClarifyingQuestion(
                        question=q.get("question", ""),
                        options=q.get("options", []),
                    )
                )
            return RoutingDecision(action="clarify", clarifying_questions=questions)

        return RoutingDecision(
            action="answer",
            complexity=data.get("complexity", "complex"),
            required_research=data.get("required_research", []),
            enriched_query=data.get("enriched_query", ""),
            response_guidance=data.get("response_guidance", ""),
        )

    def fallback_decision(self, user_message: str) -> RoutingDecision:
        """When router fails, default to complex with patch notes + web search."""
        patches = _available_patches()
        research = []
        if patches:
            research.append(
                {"tool": "load_patch_notes", "params": {"patch": patches[-1]}}
            )
        research.append(
            {"tool": "poe_web_search", "params": {"query": user_message}}
        )
        return RoutingDecision(
            action="answer",
            complexity="complex",
            required_research=research,
            enriched_query=user_message,
            response_guidance="Answer thoroughly with sourced citations.",
        )
