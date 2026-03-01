"""Central orchestrator that routes queries through the agent pipeline."""

import json
import logging
from typing import Callable, Optional

from poe_copilot.backends import LLMBackend
from poe_copilot.constants import REGISTRY_FILE
from poe_copilot.tools import _HANDLERS, TOOL_DEFINITIONS

from .agent import AgentStep, ClarifyingQuestion, NextStep, ToolStep
from .cli import STATUS_LABELS, tool_status_label
from .context import build_primer, load_loadout

logger = logging.getLogger(__name__)


class Orchestrator:
    """Central controller that routes user queries through the agent pipeline.

    Pipeline: Router → Analyst → Answerer (3 agents).

    Parameters
    ----------
    settings : dict
        User settings used to build agent primers and configure tools.
    backend : LLMBackend
        LLM backend used for all agent API calls.
    """

    def __init__(self, settings: dict, backend: LLMBackend):
        """Initialize agents, tools, and conversation state from *settings*."""
        self.settings = settings
        self.messages: list[dict] = []
        self.api_calls = 0
        self.max_api_calls = 25
        self._conversation_context: str = ""
        self._on_status: Optional[Callable[[str], None]] = None

        registry = _load_registry()

        self.steps: dict[str, AgentStep | ToolStep] = {}

        # Load agent steps
        for name, cfg in registry["agents"].items():
            tools = TOOL_DEFINITIONS if cfg.get("tools") else None

            self.steps[name] = AgentStep(
                name=name,
                primer=build_primer(name, settings),
                model=cfg["model"],
                tools=tools,
                next_agent=cfg.get("next"),
                max_tokens=cfg.get("max_tokens", 4096),
                backend=backend,
            )

        # Cache the analyst's base primer for loadout injection
        analyst_step = self.steps.get("analyst")
        self._analyst_base_primer = (
            analyst_step.primer if isinstance(analyst_step, AgentStep) else ""
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
                "IMPORTANT: The user has already answered your clarifying "
                'questions below. Do NOT return action "clarify". '
                "Classify and route to the appropriate agent.\n\n" + query
            )
        self._conversation_context = query
        self._on_status = on_status
        logger.info("CALL %s <- query", start_agent)
        decision = self._call_agent(start_agent, {"query": query})
        logger.info(
            "DECISION %s -> type=%s input_keys=%s",
            start_agent,
            decision.type,
            list(decision.input.keys()),
        )

        decision = self._step_loop(
            decision, on_status=on_status, on_message=on_message
        )

        # Terminal answer handling
        if "clarification" in decision.input:
            # Circuit breaker: don't ask again — force-route to analyst
            if clarification_round >= 1:
                logger.warning(
                    "Router re-clarified on round %d — forcing route to analyst",
                    clarification_round,
                )
                decision = self._call_agent(
                    "analyst",
                    {
                        "query": (
                            "## Conversation Context\n"
                            f"{self._conversation_context}"
                            f"\n\n## Task\n{user_message}"
                        )
                    },
                )
            else:
                logger.info("CLARIFY: %s", decision.input["clarification"])
                self.messages.pop()
                return self._parse_clarification(decision.input["clarification"])

        answer_text: str = decision.input["text"]
        logger.info("ANSWER: %s", answer_text[:500])
        self.messages.append({"role": "assistant", "content": answer_text})
        return answer_text

    def force_answer(self, extra_context: str = "") -> str:
        """Force the answerer to produce a response from available data.

        Used after ``KeyboardInterrupt`` to salvage partial results.

        Parameters
        ----------
        extra_context : str, optional
            Additional context supplied by the user at the interrupt.

        Returns
        -------
        str
            The generated answer text.
        """
        result = self._force_answerer(extra_context)
        answer_text: str = result.input["text"]
        logger.info("FORCE_ANSWER: %s", answer_text[:500])
        self.messages.append({"role": "assistant", "content": answer_text})
        return answer_text

    def _force_answerer(self, extra_context: str = "") -> NextStep:
        """Build a forced prompt, call the answerer, and apply circuit breaker."""
        if self._on_status:
            self._on_status("Writing response...")

        # Pull analyst findings from its thread (assistant msgs only)
        analyst_step = self.steps.get("analyst")
        analyst_context = "(no research collected)"
        if isinstance(analyst_step, AgentStep) and analyst_step._thread:
            parts = []
            for msg in analyst_step._thread:
                if msg.get("role") != "assistant":
                    continue
                content = msg.get("content", "")
                if isinstance(content, str) and content:
                    parts.append(content[:2000])
            if parts:
                analyst_context = "\n".join(parts[-10:])

        forced_query = (
            f"## User Question\n{self._conversation_context}\n\n"
            f"## Research Gathered So Far\n{analyst_context}\n\n"
        )
        if extra_context:
            forced_query += (
                f"## Additional Context from User\n{extra_context}\n\n"
            )
        forced_query += (
            "## Instructions\n"
            "IMPORTANT: You MUST write a final, helpful answer in "
            "markdown for the user. Do NOT output JSON or routing "
            "instructions. Synthesize the research above into a "
            "clear answer. If the research is insufficient, say so "
            "honestly and provide what you can."
        )

        answerer = self.steps["answerer"]
        if isinstance(answerer, AgentStep):
            answerer.reset()
        result = answerer.call({"query": forced_query})

        # Circuit breaker: force into terminal answer
        if result.type != "answer" or "text" not in result.input:
            logger.warning(
                "Force-answerer returned non-answer (%s), "
                "applying circuit breaker",
                result.type,
            )
            return NextStep(
                type="answer",
                input={
                    "text": (
                        "I wasn't able to gather enough information "
                        "to fully answer your question. Could you try "
                        "rephrasing or asking something more specific?"
                    )
                },
            )
        return result

    def _call_agent(self, name: str, input: dict) -> NextStep:
        """Invoke a named agent step, enforcing the API-call budget."""
        self.api_calls += 1
        if self.api_calls > self.max_api_calls:
            logger.warning(
                "API cap reached (%d), forcing answerer",
                self.max_api_calls,
            )
            return self._force_answerer()
        return self.steps[name].call(input)

    def _step_loop(
        self,
        decision: NextStep,
        *,
        on_status: Optional[Callable[[str], None]] = None,
        on_message: Optional[Callable[[str], None]] = None,
    ) -> NextStep:
        """Execute the decision-tool-route loop until a terminal answer."""
        while decision.type != "answer":
            if decision.input.get("user_msg") and on_message:
                on_message(decision.input["user_msg"])
            if on_status:
                on_status(self._status_label(decision))

            inp = decision.input

            if "tools" in inp:
                results = self._execute_tool_calls(inp["tools"])

                if on_status:
                    on_status("Analyzing results...")
                logger.info(
                    "CALL %s <- tool_results (%d)",
                    inp["return_to"],
                    len(results),
                )
                decision = self._call_agent(
                    inp["return_to"], {"tool_results": results}
                )
                logger.info(
                    "DECISION %s -> type=%s input_keys=%s",
                    inp["return_to"],
                    decision.type,
                    list(decision.input.keys()),
                )

            elif "target" in inp:
                query = inp["query"]
                target = inp["target"]
                # Inject conversation context for analyst and answerer
                if target in ("analyst", "answerer"):
                    query = (
                        "## Conversation Context\n"
                        f"{self._conversation_context}"
                        f"\n\n## Task\n{query}"
                    )
                if target == "analyst":
                    self._apply_loadout(inp.get("loadout"))
                    remaining = self.max_api_calls - self.api_calls
                    query += (
                        f"\n\n## Budget\n"
                        f"You have ~{remaining} API calls remaining."
                    )
                logger.info("CALL %s <- query", target)
                decision = self._call_agent(target, {"query": query})
                logger.info(
                    "DECISION %s -> type=%s input_keys=%s",
                    target,
                    decision.type,
                    list(decision.input.keys()),
                )

        return decision

    def _execute_tool_calls(self, tool_calls: list[dict]) -> list[dict]:
        """Execute tool calls and serialize results."""
        results = []
        for tc in tool_calls:
            if self._on_status:
                self._on_status(tool_status_label(tc["name"], tc["input"]))
            logger.info("TOOL %s input=%s", tc["name"], tc["input"])
            tool_result = self.steps[tc["name"]].call(tc["input"])
            result_content = (
                json.dumps(tool_result.input["result"])
                if isinstance(tool_result.input["result"], (dict, list))
                else str(tool_result.input["result"])
            )
            logger.info(
                "TOOL_RESULT %s (%d chars)",
                tc["name"],
                len(result_content),
            )
            results.append({"tool_use_id": tc["id"], "content": result_content})
        return results

    def _build_context(self, user_message: str) -> str:
        """Assemble recent conversation history into a context string."""
        context_parts = []
        for msg in self.messages[-7:-1]:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if isinstance(content, list):
                text_parts = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text_parts.append(block["text"])
                    elif (
                        hasattr(block, "type") and block.type == "text"  # type: ignore
                    ):
                        text_parts.append(block.text)  # type: ignore
                content = " ".join(text_parts)
            if content and isinstance(content, str):
                limit = 1500 if role == "assistant" else 300
                context_parts.append(f"{role}: {content[:limit]}")

        context_str = (
            "\n".join(context_parts) if context_parts else "(new conversation)"
        )
        return (
            f"Recent conversation:\n{context_str}"
            f"\n\nCurrent user message: {user_message}"
        )

    def _status_label(self, decision: NextStep) -> str:
        """Derive a human-friendly spinner label from a routing decision."""
        inp = decision.input
        if "target" in inp:
            return STATUS_LABELS.get(
                inp["target"], f"Running {inp['target']}..."
            )
        if "tools" in inp and inp["tools"]:
            first_tool = inp["tools"][0]
            return tool_status_label(first_tool["name"], first_tool["input"])
        return "Working..."

    def _apply_loadout(self, loadout: str | None) -> None:
        """Swap the analyst's primer to include a loadout fragment."""
        analyst_step = self.steps.get("analyst")
        if not isinstance(analyst_step, AgentStep):
            return
        if not loadout:
            analyst_step.primer = self._analyst_base_primer
            return
        fragment = load_loadout(loadout)
        if not fragment:
            logger.warning("Loadout %r not found, using base primer", loadout)
            analyst_step.primer = self._analyst_base_primer
            return
        analyst_step.primer = self._analyst_base_primer + "\n\n" + fragment

    def _parse_clarification(self, data: dict) -> list[ClarifyingQuestion]:
        """Convert raw clarification JSON into ClarifyingQuestion objects."""
        questions = []
        for q in data.get("clarifying_questions", []):
            questions.append(
                ClarifyingQuestion(
                    question=q.get("question", ""),
                    options=q.get("options", []),
                )
            )
        return questions


def _load_registry() -> dict:
    """Load the agent registry from the bundled JSON configuration."""
    data = json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Unexpected registry format: {data}")
    return data
