from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Callable, Optional

import anthropic

from .agent import AgentStep, NextStep, ToolStep, load_registry
from .context import build_primer
from .tools import _HANDLERS, TOOL_DEFINITIONS

logger = logging.getLogger(__name__)

# Friendly spinner labels per step name
_STATUS_LABELS: dict[str, str] = {
    "router": "Analyzing your question...",
    "researcher": "Researching...",
    "build_agent": "Composing build...",
    "answerer": "Writing response...",
    "get_currency_prices": "Checking currency prices",
    "get_item_prices": "Looking up item prices",
    "get_build_meta": "Checking build meta...",
    "poe_web_search": "Searching the web",
    "read_webpage": "Reading a webpage",
}


# ---------------------------------------------------------------------------
# Routing dataclasses (used by main.py UI)
# ---------------------------------------------------------------------------


@dataclass
class ClarifyingQuestion:
    question: str
    options: list[str]


@dataclass
class ClarificationRequest:
    questions: list[ClarifyingQuestion]


# ---------------------------------------------------------------------------
# Orchestrator — generic step loop
# ---------------------------------------------------------------------------


class Orchestrator:
    def __init__(self, settings: dict):
        self.settings = settings
        self.messages: list[dict] = []
        self.api_calls = 0
        self.tool_calls = 0
        self.max_api_calls = 20
        self.max_tool_calls = 15

        client = anthropic.Anthropic()
        registry = load_registry()

        self.steps: dict[str, AgentStep | ToolStep] = {}

        # Load agent steps
        for name, cfg in registry["agents"].items():
            self.steps[name] = AgentStep(
                name=name,
                primer=build_primer(name, settings),
                model=cfg["model"],
                tools=TOOL_DEFINITIONS if cfg.get("tools") else None,
                next_agent=cfg.get("next"),
                output_format=cfg.get("output_format"),
                max_tokens=cfg.get("max_tokens", 4096),
                client=client,
            )

        # Load tool steps
        for tool_name, handler in _HANDLERS.items():
            self.steps[tool_name] = ToolStep(
                name=tool_name, handler=handler, settings=settings
            )

    def run(
        self,
        user_message: str,
        on_status: Optional[Callable[[str], None]] = None,
        start_agent: str = "router",
    ) -> str | ClarificationRequest:
        self.messages.append({"role": "user", "content": user_message})
        self.api_calls = 0
        self.tool_calls = 0

        # Reset all agent threads
        for step in self.steps.values():
            if isinstance(step, AgentStep):
                step.reset()

        query = self._build_context(user_message)
        self._conversation_context = query
        decision = self._call_agent(start_agent, {"query": query})

        # Generic loop
        while decision.type != "answer":
            if on_status:
                on_status(self._status_label(decision))

            inp = decision.input

            if "tools" in inp:
                # Tool request — execute all, feed results back
                results = []
                for tool_call in inp["tools"]:
                    self.tool_calls += 1
                    self._check_cap("tool")
                    if on_status:
                        on_status(
                            _STATUS_LABELS.get(
                                tool_call["name"], f"Using {tool_call['name']}"
                            )
                        )
                    tool_result = self.steps[tool_call["name"]].call(tool_call["input"])
                    results.append(
                        {
                            "tool_use_id": tool_call["id"],
                            "content": json.dumps(tool_result.input["result"])
                            if isinstance(tool_result.input["result"], (dict, list))
                            else str(tool_result.input["result"]),
                        }
                    )
                decision = self._call_agent(inp["return_to"], {"tool_results": results})

            elif "target" in inp:
                query = inp["query"]
                if inp["target"] in ("researcher", "answerer", "build_agent"):
                    query = f"## Conversation Context\n{self._conversation_context}\n\n## Task\n{query}"
                decision = self._call_agent(inp["target"], {"query": query})

        # Terminal answer handling
        if "clarification" in decision.input:
            self.messages.pop()  # remove user message — will re-send with answers
            return ClarificationRequest(
                questions=self._parse_clarification(decision.input["clarification"])
            )

        answer_text = decision.input["text"]
        self.messages.append({"role": "assistant", "content": answer_text})
        return answer_text

    def _call_agent(self, name: str, input: dict) -> NextStep:
        self.api_calls += 1
        if self.api_calls > self.max_api_calls:
            logger.warning("API cap reached (%d), forcing answerer", self.max_api_calls)
            query = input.get("query", json.dumps(input))
            return self.steps["answerer"].call(
                {
                    "query": f"IMPORTANT: Max API calls reached. Answer as best you can with what we have.\n\n{query}"
                }
            )
        return self.steps[name].call(input)

    def _check_cap(self, kind: str):
        if kind == "tool" and self.tool_calls > self.max_tool_calls:
            raise RuntimeError(f"Tool call limit ({self.max_tool_calls}) exceeded")

    def _build_context(self, user_message: str) -> str:
        context_parts = []
        for msg in self.messages[-7:-1]:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if isinstance(content, list):
                text_parts = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text_parts.append(block["text"])
                    elif hasattr(block, "type") and block.type == "text":  # type: ignore
                        text_parts.append(block.text)  # type: ignore
                content = " ".join(text_parts)
            if content and isinstance(content, str):
                limit = 1500 if role == "assistant" else 300
                context_parts.append(f"{role}: {content[:limit]}")

        context_str = (
            "\n".join(context_parts) if context_parts else "(new conversation)"
        )
        return f"Recent conversation:\n{context_str}\n\nCurrent user message: {user_message}"

    def _status_label(self, decision: NextStep) -> str:
        inp = decision.input
        if "target" in inp:
            return _STATUS_LABELS.get(inp["target"], f"Running {inp['target']}...")
        if "tools" in inp and inp["tools"]:
            return _STATUS_LABELS.get(inp["tools"][0]["name"], "Working...")
        return "Working..."

    def _parse_clarification(self, data: dict) -> list[ClarifyingQuestion]:
        questions = []
        for q in data.get("clarifying_questions", []):
            questions.append(
                ClarifyingQuestion(
                    question=q.get("question", ""),
                    options=q.get("options", []),
                )
            )
        return questions
