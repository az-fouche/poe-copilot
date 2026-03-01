"""Central orchestrator that routes queries through the agent pipeline."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Callable, Optional

import anthropic

from ..constants import REGISTRY_FILE
from ..context import build_primer
from ..delegation import DELEGATION_TOOL_NAMES, DELEGATION_TOOLS
from ..tools import _HANDLERS, TOOL_DEFINITIONS
from .agent import AgentStep, NextStep, ToolStep

logger = logging.getLogger(__name__)

# Friendly spinner labels for agents and delegation tools
_STATUS_LABELS: dict[str, str] = {
    "router": "Analyzing your question...",
    "planner": "Planning approach...",
    "researcher": "Researching...",
    "build_agent": "Composing build...",
    "fact_checker": "Verifying facts...",
    "answerer": "Writing response...",
    "delegate_research": "Researching...",
    "delegate_build": "Composing build...",
    "delegate_fact_check": "Verifying facts...",
}


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


class Orchestrator:
    """Central controller that routes user queries through the agent pipeline.

    Manages agent and tool steps, conversation history, API budget, and
    the run-loop that chains routing decisions until a terminal answer is
    produced.

    Parameters
    ----------
    settings : dict
        User settings used to build agent primers and configure tools.
    """

    def __init__(self, settings: dict):
        """Initialize agents, tools, and conversation state from *settings*."""
        self.settings = settings
        self.messages: list[dict] = []
        self.api_calls = 0
        self.max_api_calls = 25
        self._accumulated_research: list[str] = []
        self._conversation_context: str = ""
        self._on_status: Optional[Callable[[str], None]] = None

        client = anthropic.Anthropic()
        registry = _load_registry()

        self.steps: dict[str, AgentStep | ToolStep] = {}

        # Load agent steps
        for name, cfg in registry["agents"].items():
            tools_cfg = cfg.get("tools")
            if tools_cfg == "delegation":
                tools = DELEGATION_TOOLS
            elif tools_cfg:
                tools = TOOL_DEFINITIONS
            else:
                tools = None

            self.steps[name] = AgentStep(
                name=name,
                primer=build_primer(name, settings),
                model=cfg["model"],
                tools=tools,
                next_agent=cfg.get("next"),
                max_tokens=cfg.get("max_tokens", 4096),
                client=client,
            )

        # Load tool steps
        for tool_name, handler in _HANDLERS.items():
            self.steps[tool_name] = ToolStep(name=tool_name, handler=handler, settings=settings)

    def run(
        self,
        user_message: str,
        on_status: Optional[Callable[[str], None]] = None,
        on_message: Optional[Callable[[str], None]] = None,
        start_agent: str = "router",
        clarification_round: int = 0,
    ) -> str | list[ClarifyingQuestion]:
        """Run the orchestrator pipeline for a single user message.

        Parameters
        ----------
        user_message : str
            The user's input text.
        on_status : callable or None, optional
            Callback invoked with spinner-label strings during processing.
        on_message : callable or None, optional
            Callback invoked with intermediate user-facing messages.
        start_agent : str, optional
            Name of the entry-point agent (default ``"router"``).
        clarification_round : int, optional
            Current clarification iteration (``0`` on first pass).

        Returns
        -------
        str or list[ClarifyingQuestion]
            Final answer text, or a list of clarifying questions when the
            router requests more information from the user.
        """
        logger.info("USER: %s", user_message)
        self.messages.append({"role": "user", "content": user_message})
        self.api_calls = 0

        # Reset all agent threads
        for step in self.steps.values():
            if isinstance(step, AgentStep):
                step.reset()

        query = self._build_context(user_message)
        if clarification_round > 0:
            query = (
                "IMPORTANT: The user has already answered your clarifying questions below. "
                'Do NOT return action "clarify". Classify and route to the appropriate agent.\n\n' + query
            )
        self._conversation_context = query
        self._accumulated_research: list[str] = []
        self._on_status = on_status
        logger.info("CALL %s <- query", start_agent)
        decision = self._call_agent(start_agent, {"query": query})
        logger.info("DECISION %s -> type=%s input_keys=%s", start_agent, decision.type, list(decision.input.keys()))

        decision = self._step_loop(decision, on_status=on_status, on_message=on_message)

        # Terminal answer handling
        if "clarification" in decision.input:
            # Circuit breaker: if we already clarified, don't ask again — force-route to researcher
            if clarification_round >= 1:
                logger.warning(
                    "Router re-clarified on round %d — forcing route to researcher",
                    clarification_round,
                )
                decision = self._call_agent(
                    "researcher",
                    {"query": f"## Conversation Context\n{self._conversation_context}\n\n## Task\n{user_message}"},
                )
            else:
                logger.info("CLARIFY: %s", decision.input["clarification"])
                self.messages.pop()  # remove user message — will re-send with answers
                return self._parse_clarification(decision.input["clarification"])

        answer_text = decision.input["text"]
        logger.info("ANSWER: %s", answer_text[:500])
        self.messages.append({"role": "assistant", "content": answer_text})
        return answer_text

    def force_answer(self, extra_context: str = "") -> str:
        """Force the answerer to produce a response from accumulated research.

        Used after ``KeyboardInterrupt`` to salvage partial results.

        Parameters
        ----------
        extra_context : str, optional
            Additional context supplied by the user at the interrupt prompt.

        Returns
        -------
        str
            The generated answer text.
        """
        result = self._force_answerer(extra_context)
        answer_text = result.input["text"]
        logger.info("FORCE_ANSWER: %s", answer_text[:500])
        self.messages.append({"role": "assistant", "content": answer_text})
        return answer_text

    def _force_answerer(self, extra_context: str = "") -> NextStep:
        """Build a forced prompt, call the answerer, and apply circuit breaker."""
        if self._on_status:
            self._on_status("Writing response...")

        research_summary = (
            "\n".join(self._accumulated_research[-20:]) if self._accumulated_research else "(no research collected)"
        )
        forced_query = (
            f"## User Question\n{self._conversation_context}\n\n## Research Gathered So Far\n{research_summary}\n\n"
        )
        if extra_context:
            forced_query += f"## Additional Context from User\n{extra_context}\n\n"
        forced_query += (
            "## Instructions\n"
            "IMPORTANT: You MUST write a final, helpful answer in markdown for the user. "
            "Do NOT output JSON or routing instructions. Synthesize the research above "
            "into a clear answer. If the research is insufficient, say so honestly and "
            "provide what you can."
        )

        answerer = self.steps["answerer"]
        if isinstance(answerer, AgentStep):
            answerer.reset()
        result = answerer.call({"query": forced_query})

        # Circuit breaker: if the answerer still didn't produce a terminal answer,
        # force it into one so we never loop back into research.
        if result.type != "answer" or "text" not in result.input:
            logger.warning(
                "Force-answerer returned non-answer (%s), applying circuit breaker",
                result.type,
            )
            return NextStep(
                type="answer",
                input={
                    "text": (
                        "I wasn't able to gather enough information to fully answer your question. "
                        "Could you try rephrasing or asking something more specific?"
                    )
                },
            )
        return result

    def _call_agent(self, name: str, input: dict) -> NextStep:
        """Invoke a named agent step, enforcing the API-call budget."""
        self.api_calls += 1
        if self.api_calls > self.max_api_calls:
            logger.warning("API cap reached (%d), forcing answerer", self.max_api_calls)
            return self._force_answerer()
        return self.steps[name].call(input)

    def _step_loop(
        self,
        decision: NextStep,
        *,
        on_status: Optional[Callable[[str], None]] = None,
        on_message: Optional[Callable[[str], None]] = None,
        intercept_routing: bool = False,
    ) -> NextStep | str:
        """Execute the decision-tool-route loop until a terminal answer is reached."""
        while decision.type != "answer":
            if decision.input.get("user_msg") and on_message:
                on_message(decision.input["user_msg"])
            if on_status:
                on_status(self._status_label(decision))

            inp = decision.input

            if "tools" in inp:
                delegation_calls = [tc for tc in inp["tools"] if tc["name"] in DELEGATION_TOOL_NAMES]
                regular_calls = [tc for tc in inp["tools"] if tc["name"] not in DELEGATION_TOOL_NAMES]

                results = []
                for tc in delegation_calls:
                    if on_status:
                        on_status(_STATUS_LABELS.get(tc["name"], f"Delegating {tc['name']}"))
                    logger.info("DELEGATION %s input=%s", tc["name"], tc["input"])
                    delegation_result = self._handle_delegation(tc["name"], tc["input"])
                    logger.info("DELEGATION_RESULT %s (%d chars)", tc["name"], len(delegation_result))
                    results.append({"tool_use_id": tc["id"], "content": delegation_result})
                    self._accumulated_research.append(f"[{tc['name']}] {delegation_result[:2000]}")

                results.extend(self._execute_tool_calls(regular_calls))

                # Budget check during delegation — return partial results
                if intercept_routing and self.api_calls >= self.max_api_calls:
                    logger.warning("Budget exceeded during delegation, returning partial results")
                    partial = "\n".join(r["content"][:2000] for r in results)
                    return f"(partial results — budget exceeded)\n{partial}"

                if on_status:
                    on_status("Analyzing results...")
                logger.info("CALL %s <- tool_results (%d)", inp["return_to"], len(results))
                decision = self._call_agent(inp["return_to"], {"tool_results": results})
                logger.info(
                    "DECISION %s -> type=%s input_keys=%s", inp["return_to"], decision.type, list(decision.input.keys())
                )

            elif "target" in inp:
                if intercept_routing:
                    logger.info("DELEGATION_INTERCEPT -> %s (capturing output)", inp["target"])
                    return inp["query"]

                query = inp["query"]
                target = inp["target"]
                # Agents that need conversation context injected (static — matches registry)
                if target in ("researcher", "answerer", "build_agent", "planner"):
                    query = f"## Conversation Context\n{self._conversation_context}\n\n## Task\n{query}"
                # Inject budget info when routing to planner
                if target == "planner":
                    remaining = self.max_api_calls - self.api_calls
                    budget_info = (
                        f"## Budget\n"
                        f"You have ~{remaining} API calls remaining (out of {self.max_api_calls}). "
                        f"Research: ~3-6 calls, build: ~4-8, fact check: 1.\n\n"
                    )
                    query = budget_info + query
                logger.info("CALL %s <- query", target)
                decision = self._call_agent(target, {"query": query})
                logger.info("DECISION %s -> type=%s input_keys=%s", target, decision.type, list(decision.input.keys()))

        if intercept_routing:
            return decision.input.get("text", str(decision.input))
        return decision

    def _execute_tool_calls(self, tool_calls: list[dict]) -> list[dict]:
        """Execute regular tool calls, serialize results, and accumulate research."""
        results = []
        for tc in tool_calls:
            if self._on_status:
                self._on_status(_tool_status_label(tc["name"], tc["input"]))
            logger.info("TOOL %s input=%s", tc["name"], tc["input"])
            tool_result = self.steps[tc["name"]].call(tc["input"])
            result_content = (
                json.dumps(tool_result.input["result"])
                if isinstance(tool_result.input["result"], (dict, list))
                else str(tool_result.input["result"])
            )
            logger.info("TOOL_RESULT %s (%d chars)", tc["name"], len(result_content))
            results.append({"tool_use_id": tc["id"], "content": result_content})
            self._accumulated_research.append(f"[{tc['name']}] {result_content[:2000]}")
        return results

    def _handle_delegation(self, tool_name: str, tool_input: dict) -> str:
        """Map delegation tool calls to sub-agent runs."""
        if tool_name == "delegate_research":
            return self._run_agent_to_completion("researcher", tool_input["task"])
        elif tool_name == "delegate_build":
            task = tool_input["task"]
            context = tool_input.get("context", "")
            if context:
                task = f"## Prior Research\n{context}\n\n## Task\n{task}"
            return self._run_agent_to_completion("build_agent", task)
        elif tool_name == "delegate_fact_check":
            # Single-shot call — fact checker has no tools, no loop needed
            query = (
                f"## Original Question\n{tool_input['original_question']}\n\n"
                f"## Research to Verify\n{tool_input['research']}"
            )
            result = self._call_agent("fact_checker", {"query": query})
            return result.input.get("text", str(result.input))
        else:
            return f"Unknown delegation tool: {tool_name}"

    def _run_agent_to_completion(self, agent_name: str, task: str) -> str:
        """Run a sub-agent to completion, intercepting its terminal routing decision."""
        agent_step = self.steps[agent_name]
        assert isinstance(agent_step, AgentStep)

        # Fresh start for this delegation
        agent_step.reset()

        # Inject conversation context
        query = f"## Conversation Context\n{self._conversation_context}\n\n## Task\n{task}"
        decision = self._call_agent(agent_name, {"query": query})

        return self._step_loop(decision, on_status=self._on_status, intercept_routing=True)

    def _build_context(self, user_message: str) -> str:
        """Assemble recent conversation history into a context string for the router."""
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

        context_str = "\n".join(context_parts) if context_parts else "(new conversation)"
        return f"Recent conversation:\n{context_str}\n\nCurrent user message: {user_message}"

    def _status_label(self, decision: NextStep) -> str:
        """Derive a human-friendly spinner label from a routing decision."""
        inp = decision.input
        if "target" in inp:
            return _STATUS_LABELS.get(inp["target"], f"Running {inp['target']}...")
        if "tools" in inp and inp["tools"]:
            first_tool = inp["tools"][0]
            if first_tool["name"] in DELEGATION_TOOL_NAMES:
                return _STATUS_LABELS.get(first_tool["name"], "Delegating...")
            return _tool_status_label(first_tool["name"], first_tool["input"])
        return "Working..."

    def _parse_clarification(self, data: dict) -> list[ClarifyingQuestion]:
        """Convert raw clarification JSON into a list of ClarifyingQuestion objects."""
        questions = []
        for q in data.get("clarifying_questions", []):
            questions.append(
                ClarifyingQuestion(
                    question=q.get("question", ""),
                    options=q.get("options", []),
                )
            )
        return questions


def _truncate(text: str, max_len: int) -> str:
    """Truncate text to a maximum length, adding an ellipsis if truncated."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "\u2026"


def _tool_status_label(name: str, tool_input: dict) -> str:
    """Build a dynamic spinner label based on tool name and its inputs."""
    if name == "read_webpage":
        url = tool_input.get("url", "")
        section = tool_input.get("section", "")
        short_url = url.replace("https://", "").replace("http://", "")
        if section:
            return f'Reading "{_truncate(section, 25)}" from {_truncate(short_url, 30)}'
        return f"Reading {_truncate(short_url, 45)}"

    if name == "poe_web_search":
        query = tool_input.get("query", "")
        if query:
            return f"Searching: {_truncate(query, 45)}"
        return "Searching the web..."

    if name == "get_item_prices":
        name_filter = tool_input.get("name", "")
        item_type = tool_input.get("type", "")
        if name_filter:
            return f'Looking up "{_truncate(name_filter, 30)}" prices...'
        if item_type:
            return f"Looking up {_truncate(item_type, 30)} prices..."
        return "Looking up item prices..."

    if name == "get_build_meta":
        class_filter = tool_input.get("class_filter", "")
        if class_filter:
            return f"Checking {class_filter} build meta..."
        return "Checking build meta..."

    if name == "get_currency_prices":
        return "Checking currency prices..."

    return f"Using {name}..."


def _load_registry() -> dict:
    """Load the agent registry from the bundled JSON configuration."""
    return json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
