from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Callable, Optional

import anthropic

from .primer import build_system_prompt
from .router import HAIKU_MODEL, ClarifyingQuestion, Router, RoutingDecision
from .tools import TOOL_DEFINITIONS, execute_tool

logger = logging.getLogger(__name__)

SONNET_MODEL = "claude-sonnet-4-20250514"

# Friendly labels for each tool so the spinner feels human
_TOOL_LABELS: dict[str, str] = {
    "get_currency_prices": "Checking currency prices",
    "get_item_prices": "Looking up item prices",
    "poe_web_search": "Searching the web",
    "read_webpage": "Reading a webpage",
    "load_patch_notes": "Reviewing patch notes",
}


@dataclass
class ClarificationRequest:
    """Returned by chat() when the router needs more info from the user."""

    questions: list[ClarifyingQuestion]


class PoeAgent:
    def __init__(
        self,
        settings: dict,
        model: str = SONNET_MODEL,
    ):
        self.client = anthropic.Anthropic()
        self.model = model
        self.settings = settings
        self.messages: list[dict] = []
        self.system_prompt = build_system_prompt(settings)
        self.router = Router(settings=settings, client=self.client)

    def chat(
        self,
        user_message: str,
        on_status: Optional[Callable[[str], None]] = None,
        skip_router: bool = False,
    ) -> str | ClarificationRequest:
        self.messages.append({"role": "user", "content": user_message})

        def _status(text: str):
            if on_status:
                on_status(text)

        # --- Step 1: Route the request ---
        if skip_router:
            # After clarification, skip routing and go straight to answer
            _status("Researching...")
            decision = self.router.fallback_decision(user_message)
        else:
            _status("Analyzing your question...")
            decision = self.router.route(user_message, self.messages[:-1])

            # --- Step 2: Handle clarification ---
            if decision.action == "clarify" and decision.clarifying_questions:
                # Remove the message we just added — it'll be re-sent with context
                self.messages.pop()
                return ClarificationRequest(questions=decision.clarifying_questions)

        # --- Step 3: Pre-fetch required research ---
        prefetched = self._prefetch_research(decision, _status)

        # --- Step 4: Build enriched context and call answering model ---
        return self._answer(decision, prefetched, _status)

    def _prefetch_research(
        self,
        decision: RoutingDecision,
        _status: Callable[[str], None],
    ) -> list[dict]:
        """Execute router-specified tool calls and return results."""
        results = []
        for spec in decision.required_research:
            tool_name = spec.get("tool", "")
            params = spec.get("params", {})
            label = _TOOL_LABELS.get(tool_name, f"Using {tool_name}")
            _status(label)
            try:
                result = execute_tool(tool_name, params, self.settings)
                results.append({"tool": tool_name, "params": params, "result": result})
            except Exception as e:
                logger.warning("Pre-fetch failed for %s: %s", tool_name, e)
                results.append(
                    {"tool": tool_name, "params": params, "result": {"error": str(e)}}
                )
        return results

    def _answer(
        self,
        decision: RoutingDecision,
        prefetched: list[dict],
        _status: Callable[[str], None],
    ) -> str:
        """Call the answering model with pre-fetched context, then run agentic loop."""
        # Pick model based on complexity
        model = HAIKU_MODEL if decision.complexity == "simple" else self.model

        # Build pre-fetched research context to inject into the conversation
        research_parts = []
        for item in prefetched:
            tool = item["tool"]
            result = item["result"]
            result_str = json.dumps(result) if isinstance(result, (dict, list)) else str(result)
            research_parts.append(f"[Pre-fetched: {tool}]\n{result_str}")

        if research_parts or decision.enriched_query or decision.response_guidance:
            context_block = []
            if decision.enriched_query:
                context_block.append(f"Enriched query: {decision.enriched_query}")
            if decision.response_guidance:
                context_block.append(f"Response guidance: {decision.response_guidance}")
            if research_parts:
                context_block.append(
                    "Pre-fetched research (use these results — they are fresh and accurate):\n\n"
                    + "\n\n---\n\n".join(research_parts)
                )

            # Inject pre-fetched context as a system-like user message
            # We append it as additional context on the last user message
            context_text = "\n\n".join(context_block)
            last_msg = self.messages[-1]
            if isinstance(last_msg["content"], str):
                self.messages[-1] = {
                    "role": "user",
                    "content": (
                        f"{last_msg['content']}\n\n"
                        f"<research_context>\n{context_text}\n</research_context>"
                    ),
                }

        _status("Thinking...")
        loop_count = 0

        # Agentic loop: keep going until we get a final text response
        while True:
            loop_count += 1
            if loop_count > 1:
                _status("Digging deeper...")

            response = self.client.messages.create(
                model=model,
                max_tokens=4096,
                system=[
                    {
                        "type": "text",
                        "text": self.system_prompt,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                tools=TOOL_DEFINITIONS,
                messages=self.messages,
            )

            self.messages.append({"role": "assistant", "content": response.content})

            # Check for tool use
            tool_uses = [b for b in response.content if b.type == "tool_use"]

            if not tool_uses:
                _status("Wrapping up...")
                text_parts = [b.text for b in response.content if b.type == "text"]
                return "\n".join(text_parts)

            # Execute follow-up tool calls from the answering model
            tool_results = []
            for tool_use in tool_uses:
                label = _TOOL_LABELS.get(tool_use.name, f"Using {tool_use.name}")
                _status(label)
                result = execute_tool(tool_use.name, tool_use.input, self.settings)
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": json.dumps(result)
                        if isinstance(result, (dict, list))
                        else str(result),
                    }
                )

            self.messages.append({"role": "user", "content": tool_results})
