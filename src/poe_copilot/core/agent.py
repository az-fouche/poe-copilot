"""Agent step abstractions for the orchestrator pipeline."""

import json
import logging
from dataclasses import dataclass
from typing import Any, Callable

from poe_copilot.backends import LLMBackend, ToolUseBlock

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# NextStep — the only return type from any step
# ---------------------------------------------------------------------------


@dataclass
class NextStep:
    """Uniform return type produced by every pipeline step.

    Attributes
    ----------
    type : str
        Step outcome kind — ``"answer"`` for a terminal response or
        ``"call"`` to invoke another step.
    input : dict[str, Any]
        Payload forwarded to the next consumer.  Keys vary by *type*:
        ``"text"`` for answers, ``"target"``/``"query"`` for routing,
        ``"tools"`` for tool-use requests.
    """

    type: str  # "answer" | "call"
    input: dict[str, Any]


@dataclass
class ClarifyingQuestion:
    """A question posed to the user before routing to a specialist agent.

    Attributes
    ----------
    question : str
        The clarifying question text.
    options : list[str]
        Suggested answer choices presented to the user.
    """

    question: str
    options: list[str]


# ---------------------------------------------------------------------------
# AgentStep — wraps one Claude agent
# ---------------------------------------------------------------------------


class AgentStep:
    """Pipeline step that wraps a single LLM conversational agent.

    Maintains a per-run message thread and delegates to an ``LLMBackend``.
    Tool-use blocks are surfaced as ``NextStep(type="call")``;
    plain text is parsed for JSON routing instructions.

    Parameters
    ----------
    name : str
        Identifier used for logging and routing (e.g. ``"router"``).
    primer : str
        System prompt sent with every API request.
    model : str
        Model identifier (e.g. ``"claude-sonnet-4-20250514"``).
    backend : LLMBackend
        Shared LLM backend (Anthropic, OpenAI, etc.) used to make API calls.
    tools : list or None, optional
        Tool definitions passed to the API.  ``None`` disables tool use.
    next_agent : str or None, optional
        Default routing target when the response contains no explicit target.
    max_tokens : int, optional
        Maximum completion tokens (default ``4096``).
    """

    def __init__(
        self,
        name: str,
        primer: str,
        model: str,
        backend: LLMBackend,
        tools: list | None = None,
        next_agent: str | None = None,
        max_tokens: int = 4096,
    ):
        """Initialize the agent step and create an empty message thread."""
        self.name = name
        self.primer = primer
        self.model = model
        self.tools = tools
        self.next_agent = next_agent
        self.max_tokens = max_tokens
        self.backend = backend
        self._thread: list[dict] = []

    def reset(self) -> None:
        """Clear the message thread so the step can be reused for a new run."""
        self._thread.clear()

    def call(self, input: dict[str, Any]) -> NextStep:
        """Execute one API round-trip and return the next routing decision.

        Parameters
        ----------
        input : dict[str, Any]
            Must contain either ``"query"`` (start a new turn) or
            ``"tool_results"`` (continue after tool execution).

        Returns
        -------
        NextStep
            A routing decision: tool calls to execute, another agent to
            invoke, a clarification request, or a terminal answer.
        """
        # Build thread
        if "query" in input:
            self._thread = [{"role": "user", "content": input["query"]}]
        elif "tool_results" in input:
            self._thread.append(
                {
                    "role": "user",
                    "content": [
                        {"type": "tool_result", **r}
                        for r in input["tool_results"]
                    ],
                }
            )

        # Single API call
        logger.debug(
            "API_REQ [%s] model=%s msgs=%d",
            self.name,
            self.model,
            len(self._thread),
        )
        blocks = self.backend.complete(
            model=self.model,
            max_tokens=self.max_tokens,
            system=self.primer,
            messages=self._thread,
            tools=self.tools,
        )
        logger.debug(
            "API_RES [%s] blocks=%d",
            self.name,
            len(blocks),
        )
        self._thread.append({"role": "assistant", "content": blocks})

        # Check for tool_use blocks
        tool_calls = [b for b in blocks if isinstance(b, ToolUseBlock)]
        if tool_calls:
            logger.debug(
                "API_RES [%s] tool_use: %s",
                self.name,
                [t.name for t in tool_calls],
            )
            # Extract any accompanying text for user-facing status
            text_parts = [b for b in blocks if isinstance(b, str)]
            text = "\n".join(text_parts).strip()
            inp: dict[str, Any] = {
                "tools": [
                    {"id": t.id, "name": t.name, "input": t.input}
                    for t in tool_calls
                ],
                "return_to": self.name,
            }
            if text:
                inp["user_msg"] = text
            return NextStep(type="call", input=inp)

        # Text response
        text_parts = [b for b in blocks if isinstance(b, str)]
        text = "\n".join(text_parts).strip()
        logger.debug("API_RES [%s] text: %s", self.name, text[:500])

        result = self._handle_decision_json(text)
        logger.debug(
            "ROUTE [%s] -> type=%s input_keys=%s",
            self.name,
            result.type,
            list(result.input.keys()),
        )
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
            candidate = text[start : end + 1]
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
        """Parse a text response for JSON routing instructions and return a NextStep."""
        # Strip markdown fences if present
        cleaned = text
        if cleaned.startswith("```"):
            cleaned = (
                cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
            )
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            # Full-text parse failed — try to extract embedded routing JSON
            data = self._extract_json(text)
            if data is None:
                logger.debug(
                    "decision_json parse failed, treating as plain text"
                )
                if self.next_agent:
                    return NextStep(
                        type="call",
                        input={"target": self.next_agent, "query": text},
                    )
                return NextStep(type="answer", input={"text": text})

        if data.get("action") == "clarify":
            return NextStep(type="answer", input={"clarification": data})

        # Use target from JSON if present, otherwise fall back to next_agent
        target = data.get("target", self.next_agent)
        query = data.get("query") or data.get("enriched_query") or text
        user_msg = data.get("user_msg")
        loadout = data.get("loadout")
        if target:
            inp = {"target": target, "query": query}
            if user_msg:
                inp["user_msg"] = user_msg
            if loadout:
                inp["loadout"] = loadout
            return NextStep(type="call", input=inp)
        return NextStep(type="answer", input={"text": text})


# ---------------------------------------------------------------------------
# ToolStep — wraps one tool
# ---------------------------------------------------------------------------


class ToolStep:
    """Pipeline step that executes an external tool handler.

    Wraps a callable tool handler so it conforms to the same ``call``
    interface as `AgentStep`, letting the orchestrator treat agents and
    tools uniformly.

    Parameters
    ----------
    name : str
        Tool name matching the API tool-use block (e.g. ``"get_item_prices"``).
    handler : Callable
        Function with signature ``(name, params, settings) -> dict``.
    settings : dict
        User settings forwarded to the handler on every call.
    """

    def __init__(self, name: str, handler: Callable, settings: dict):
        """Store the handler reference and user settings."""
        self.name = name
        self.handler = handler
        self.settings = settings

    def call(self, input: dict[str, Any]) -> NextStep:
        """Run the tool handler and wrap its output in a NextStep.

        Parameters
        ----------
        input : dict[str, Any]
            Tool-specific parameters forwarded to the handler.

        Returns
        -------
        NextStep
            Always ``type="answer"`` with the handler's result dict under
            ``input["result"]``.
        """
        try:
            result = self.handler(self.name, input, self.settings)
        except Exception as e:
            logger.warning("Tool %s failed: %s", self.name, e)
            result = {"error": str(e)}
        return NextStep(type="answer", input={"result": result})
