from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import anthropic

logger = logging.getLogger(__name__)

_REGISTRY_PATH = Path(__file__).resolve().parent / "agents" / "registry.json"


def load_registry() -> dict:
    return json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# NextStep — the only return type from any step
# ---------------------------------------------------------------------------

@dataclass
class NextStep:
    type: str                        # "answer" | "call"
    input: dict[str, Any]
    history: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# AgentStep — wraps one Claude agent
# ---------------------------------------------------------------------------

class AgentStep:
    def __init__(
        self,
        name: str,
        primer: str,
        model: str,
        tools: list | None = None,
        next_agent: str | None = None,
        output_format: str | None = None,
        max_tokens: int = 4096,
        client: anthropic.Anthropic | None = None,
    ):
        self.name = name
        self.primer = primer
        self.model = model
        self.tools = tools
        self.next_agent = next_agent
        self.output_format = output_format
        self.max_tokens = max_tokens
        self.client = client or anthropic.Anthropic()
        self._thread: list[dict] = []

    def reset(self):
        self._thread.clear()

    def call(self, input: dict[str, Any]) -> NextStep:
        # Build thread
        if "query" in input:
            self._thread = [{"role": "user", "content": input["query"]}]
        elif "tool_results" in input:
            self._thread.append({
                "role": "user",
                "content": [
                    {"type": "tool_result", **r} for r in input["tool_results"]
                ],
            })

        # Single API call
        logger.debug("API_REQ [%s] model=%s msgs=%d", self.name, self.model, len(self._thread))
        kwargs: dict = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": [{"type": "text", "text": self.primer, "cache_control": {"type": "ephemeral"}}],
            "messages": self._thread,
        }
        if self.tools:
            kwargs["tools"] = self.tools

        response = self.client.messages.create(**kwargs)
        logger.debug("API_RES [%s] stop=%s blocks=%d", self.name, response.stop_reason, len(response.content))
        self._thread.append({"role": "assistant", "content": response.content})

        # Check for tool_use blocks
        tool_calls = [b for b in response.content if getattr(b, "type", None) == "tool_use"]
        if tool_calls:
            logger.debug("API_RES [%s] tool_use: %s", self.name, [t.name for t in tool_calls])
            return NextStep(
                type="call",
                input={
                    "tools": [{"id": t.id, "name": t.name, "input": t.input} for t in tool_calls],
                    "return_to": self.name,
                },
            )

        # Text response
        text_parts = [b.text for b in response.content if getattr(b, "type", None) == "text"]
        text = "\n".join(text_parts).strip()
        logger.debug("API_RES [%s] text: %s", self.name, text[:500])

        result = self._handle_decision_json(text)
        logger.debug("ROUTE [%s] -> type=%s input_keys=%s", self.name, result.type, list(result.input.keys()))
        return result

    @staticmethod
    def _extract_json(text: str) -> dict | None:
        """Scan text for an embedded JSON routing object when full-text parse fails."""
        end = text.rfind("}")
        if end == -1:
            return None
        # Walk backwards through candidate '{' positions
        start = end
        while True:
            start = text.rfind("{", 0, start)
            if start == -1:
                return None
            candidate = text[start:end + 1]
            try:
                data = json.loads(candidate)
            except json.JSONDecodeError:
                # Try an earlier '{' on next iteration
                continue
            if isinstance(data, dict) and ("action" in data or "target" in data):
                return data
            # Valid JSON but not a routing object — keep looking
            continue
        return None

    def _handle_decision_json(self, text: str) -> NextStep:
        # Strip markdown fences if present
        cleaned = text
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            # Full-text parse failed — try to extract embedded routing JSON
            data = self._extract_json(text)
            if data is None:
                logger.debug("decision_json parse failed, treating as plain text")
                if self.next_agent:
                    return NextStep(type="call", input={"target": self.next_agent, "query": text})
                return NextStep(type="answer", input={"text": text})

        if data.get("action") == "clarify":
            return NextStep(type="answer", input={"clarification": data})

        # Use target from JSON if present, otherwise fall back to next_agent
        target = data.get("target", self.next_agent)
        query = data.get("query") or data.get("enriched_query") or text
        user_msg = data.get("user_msg")
        if target:
            inp = {"target": target, "query": query}
            if user_msg:
                inp["user_msg"] = user_msg
            return NextStep(type="call", input=inp)
        return NextStep(type="answer", input={"text": text})


# ---------------------------------------------------------------------------
# ToolStep — wraps one tool
# ---------------------------------------------------------------------------

class ToolStep:
    def __init__(self, name: str, handler: Callable, settings: dict):
        self.name = name
        self.handler = handler
        self.settings = settings

    def call(self, input: dict[str, Any]) -> NextStep:
        try:
            result = self.handler(self.name, input, self.settings)
        except Exception as e:
            logger.warning("Tool %s failed: %s", self.name, e)
            result = {"error": str(e)}
        return NextStep(type="answer", input={"result": result})
