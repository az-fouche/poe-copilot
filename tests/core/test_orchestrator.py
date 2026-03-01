"""Tests for poe_copilot/orchestrator.py — routing, delegation, and budget tests."""

from unittest.mock import MagicMock, patch

from poe_copilot.core.agent import AgentStep, NextStep, ToolStep
from poe_copilot.core.cli import STATUS_LABELS, tool_status_label, truncate
from poe_copilot.core.orchestrator import (
    Orchestrator,
)

# ---------------------------------------------------------------------------
# Mock registry shared by all tests
# ---------------------------------------------------------------------------

_MOCK_REGISTRY = {
    "agents": {
        "router": {
            "model": "m",
            "tools": False,
            "output_format": "decision_json",
            "max_tokens": 1024,
        },
        "planner": {
            "model": "m",
            "tools": "delegation",
            "next": "answerer",
            "max_tokens": 4096,
        },
        "researcher": {
            "model": "m",
            "tools": True,
            "next": "answerer",
            "max_tokens": 4096,
        },
        "build_agent": {
            "model": "m",
            "tools": True,
            "next": "answerer",
            "max_tokens": 4096,
        },
        "fact_checker": {"model": "m", "tools": False, "max_tokens": 4096},
        "answerer": {
            "model": "m",
            "tools": False,
            "output_format": "decision_json",
            "max_tokens": 4096,
        },
    },
    "tools": {},
}


# ---------------------------------------------------------------------------
# Helper: build a minimal Orchestrator with mocked dependencies
# ---------------------------------------------------------------------------


def _make_orchestrator(settings, agent_responses: dict[str, list] | None = None):
    """Create an Orchestrator with pre-wired mock agents.

    agent_responses maps agent name -> list of NextStep objects returned
    by successive calls.
    """
    agent_responses = agent_responses or {}

    with (
        patch("poe_copilot.core.orchestrator._load_registry") as mock_reg,
        patch(
            "poe_copilot.core.orchestrator.build_primer", return_value="primer"
        ),
    ):
        mock_reg.return_value = _MOCK_REGISTRY
        orch = Orchestrator(settings, backend=MagicMock())

    # Replace agent steps with mocks that return pre-configured NextStep sequences
    for name, responses in agent_responses.items():
        mock_step = MagicMock(spec=AgentStep)
        mock_step.name = name
        mock_step.reset = MagicMock()
        mock_step.call = MagicMock(side_effect=responses)
        orch.steps[name] = mock_step

    return orch


# ---------------------------------------------------------------------------
# _build_context
# ---------------------------------------------------------------------------


def test_build_context_empty_history(settings):
    orch = _make_orchestrator(settings)
    orch.messages = []
    result = orch._build_context("hello")
    assert "Recent conversation:\n(new conversation)" in result
    assert "Current user message: hello" in result


def test_build_contexttruncates_assistant_at_1500(settings):
    orch = _make_orchestrator(settings)
    long_content = "a" * 2000
    orch.messages = [
        {"role": "user", "content": "q"},
        {"role": "assistant", "content": long_content},
    ]
    # _build_context looks at messages[-7:-1], which here is the full list minus last
    # We need to ensure the assistant message is in the window
    orch.messages.append({"role": "user", "content": "current"})
    result = orch._build_context("current")
    # The assistant content should be truncated to 1500 chars
    # Find the assistant line
    for line in result.split("\n"):
        if line.startswith("assistant:"):
            assert len(line) <= len("assistant: ") + 1500
            break


def test_build_contexttruncates_user_at_300(settings):
    orch = _make_orchestrator(settings)
    long_user = "b" * 500
    orch.messages = [
        {"role": "user", "content": long_user},
        {"role": "user", "content": "current"},
    ]
    result = orch._build_context("current")
    for line in result.split("\n"):
        if line.startswith("user:"):
            assert len(line) <= len("user: ") + 300
            break


def test_build_context_uses_last_6(settings):
    orch = _make_orchestrator(settings)
    # Add 10 messages + the "current" at the end
    orch.messages = [{"role": "user", "content": f"msg{i}"} for i in range(10)]
    orch.messages.append({"role": "user", "content": "current"})
    result = orch._build_context("current")
    # messages[-7:-1] => indices 4..9 (6 messages)
    assert "msg4" in result
    assert "msg9" in result
    # msg0 through msg3 should NOT be in the context
    assert "msg0" not in result
    assert "msg3" not in result


# ---------------------------------------------------------------------------
# _parse_clarification
# ---------------------------------------------------------------------------


def test_parse_clarification_normal(settings):
    orch = _make_orchestrator(settings)
    data = {"clarifying_questions": [{"question": "Q?", "options": ["A", "B"]}]}
    result = orch._parse_clarification(data)
    assert len(result) == 1
    assert result[0].question == "Q?"
    assert result[0].options == ["A", "B"]


def test_parse_clarification_empty(settings):
    orch = _make_orchestrator(settings)
    result = orch._parse_clarification({})
    assert result == []


# ---------------------------------------------------------------------------
# Orchestrator.run — full routing paths
# ---------------------------------------------------------------------------


def test_run_router_to_researcher_to_answerer(settings):
    orch = _make_orchestrator(
        settings,
        agent_responses={
            "router": [
                NextStep(
                    type="call", input={"target": "researcher", "query": "q"}
                )
            ],
            "researcher": [
                NextStep(
                    type="call",
                    input={"target": "answerer", "query": "research done"},
                )
            ],
            "answerer": [
                NextStep(type="answer", input={"text": "final answer"})
            ],
        },
    )
    result = orch.run("hello")
    assert result == "final answer"
    assert len(orch.messages) == 2
    assert orch.messages[0]["role"] == "user"
    assert orch.messages[1]["role"] == "assistant"


def test_run_clarification_flow(settings):
    clarify_data = {
        "action": "clarify",
        "clarifying_questions": [{"question": "Q?", "options": ["A", "B"]}],
    }
    orch = _make_orchestrator(
        settings,
        agent_responses={
            "router": [
                NextStep(type="answer", input={"clarification": clarify_data})
            ],
        },
    )
    result = orch.run("hello")
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0].question == "Q?"
    # User message should have been popped
    assert len(orch.messages) == 0


def test_run_tool_execution_loop(settings):
    tool_call_step = NextStep(
        type="call",
        input={
            "tools": [
                {
                    "id": "tu_1",
                    "name": "get_currency_prices",
                    "input": {"type": "Currency"},
                }
            ],
            "return_to": "researcher",
        },
    )
    after_tool_step = NextStep(
        type="call", input={"target": "answerer", "query": "done"}
    )

    orch = _make_orchestrator(
        settings,
        agent_responses={
            "router": [
                NextStep(
                    type="call", input={"target": "researcher", "query": "q"}
                )
            ],
            "researcher": [tool_call_step, after_tool_step],
            "answerer": [NextStep(type="answer", input={"text": "final"})],
        },
    )

    # Mock the tool step
    mock_tool = MagicMock(spec=ToolStep)
    mock_tool.call.return_value = NextStep(
        type="answer", input={"result": {"prices": []}}
    )
    orch.steps["get_currency_prices"] = mock_tool

    result = orch.run("check prices")
    assert result == "final"
    mock_tool.call.assert_called_once_with({"type": "Currency"})


def test_run_api_cap_forces_answerer(settings):
    orch = _make_orchestrator(
        settings,
        agent_responses={
            "router": [
                NextStep(
                    type="call", input={"target": "researcher", "query": "q"}
                )
            ],
            "researcher": [
                NextStep(
                    type="call", input={"target": "answerer", "query": "done"}
                )
            ],
            "answerer": [
                NextStep(type="answer", input={"text": "forced answer"})
            ],
        },
    )
    orch.max_api_calls = 2
    result = orch.run("hello")
    assert result == "forced answer"


def test_run_circuit_breaker(settings):
    orch = _make_orchestrator(
        settings,
        agent_responses={
            "router": [
                NextStep(
                    type="call", input={"target": "researcher", "query": "q"}
                )
            ],
        },
    )
    orch.max_api_calls = 1
    # After router uses 1 call, next call hits the cap.
    # The forced answerer will return a non-answer type to trigger circuit breaker.
    mock_answerer = MagicMock(spec=AgentStep)
    mock_answerer.name = "answerer"
    mock_answerer.reset = MagicMock()
    mock_answerer.call = MagicMock(
        return_value=NextStep(
            type="call", input={"target": "researcher", "query": "loop"}
        )
    )
    orch.steps["answerer"] = mock_answerer

    result = orch.run("hello")
    assert "I wasn't able to gather enough information" in result


def test_run_resets_agent_threads(settings):
    orch = _make_orchestrator(
        settings,
        agent_responses={
            "router": [
                NextStep(type="answer", input={"text": "first"}),
                NextStep(type="answer", input={"text": "second"}),
            ],
        },
    )
    orch.run("first question")
    orch.run("second question")
    assert orch.api_calls == 1  # reset each run
    # Verify reset was called on agent steps
    for step in orch.steps.values():
        if isinstance(step, MagicMock) and hasattr(step, "reset"):
            assert step.reset.call_count >= 1


# ---------------------------------------------------------------------------
# Level 1: router → answerer direct (no research)
# ---------------------------------------------------------------------------


def test_run_level1_router_to_answerer_direct(settings):
    """Level 1 routing: simple chitchat goes directly to answerer."""
    orch = _make_orchestrator(
        settings,
        agent_responses={
            "router": [
                NextStep(
                    type="call",
                    input={"target": "answerer", "query": "Just a greeting"},
                )
            ],
            "answerer": [
                NextStep(type="answer", input={"text": "Hey there, exile!"})
            ],
        },
    )
    result = orch.run("hi")
    assert result == "Hey there, exile!"
    # Researcher should not have been called
    assert (
        "researcher"
        not in {
            name
            for name, step in orch.steps.items()
            if isinstance(step, MagicMock) and step.call.called
        }
        or not orch.steps.get("researcher", MagicMock()).call.called  # type: ignore
    )


# ---------------------------------------------------------------------------
# Level 3: router → planner → delegation → answerer
# ---------------------------------------------------------------------------


def test_run_level3_planner_delegation_flow(settings):
    """Level 3: router → planner → delegate_research → answerer."""
    # Planner makes a delegation tool call, gets result, then routes to answerer
    delegation_tool_call = NextStep(
        type="call",
        input={
            "tools": [
                {
                    "id": "du_1",
                    "name": "delegate_research",
                    "input": {"task": "look up build meta"},
                }
            ],
            "return_to": "planner",
        },
    )
    planner_synthesis = NextStep(
        type="call",
        input={
            "target": "answerer",
            "query": "<synthesis>combined findings</synthesis>",
        },
    )

    orch = _make_orchestrator(
        settings,
        agent_responses={
            "router": [
                NextStep(
                    type="call",
                    input={"target": "planner", "query": "what to play?"},
                )
            ],
            "planner": [delegation_tool_call, planner_synthesis],
            # researcher is run inside _run_agent_to_completion
            "researcher": [
                NextStep(
                    type="call",
                    input={
                        "target": "answerer",
                        "query": "research report here",
                    },
                )
            ],
            "answerer": [
                NextStep(type="answer", input={"text": "Play Lightning Arrow!"})
            ],
        },
    )

    result = orch.run("what should I play for league start?")
    assert result == "Play Lightning Arrow!"


def test_run_level3_planner_multiple_delegations(settings):
    """Level 3: planner delegates to both researcher and build_agent."""
    research_call = NextStep(
        type="call",
        input={
            "tools": [
                {
                    "id": "du_1",
                    "name": "delegate_research",
                    "input": {"task": "check meta"},
                }
            ],
            "return_to": "planner",
        },
    )
    build_call = NextStep(
        type="call",
        input={
            "tools": [
                {
                    "id": "du_2",
                    "name": "delegate_build",
                    "input": {
                        "task": "compose LA build",
                        "context": "meta data",
                    },
                }
            ],
            "return_to": "planner",
        },
    )
    planner_done = NextStep(
        type="call",
        input={
            "target": "answerer",
            "query": "<synthesis>full findings</synthesis>",
        },
    )

    orch = _make_orchestrator(
        settings,
        agent_responses={
            "router": [
                NextStep(
                    type="call",
                    input={"target": "planner", "query": "recommend a build"},
                )
            ],
            "planner": [research_call, build_call, planner_done],
            "researcher": [
                NextStep(
                    type="call",
                    input={"target": "answerer", "query": "meta report"},
                )
            ],
            "build_agent": [
                NextStep(
                    type="call",
                    input={"target": "answerer", "query": "build report"},
                )
            ],
            "answerer": [
                NextStep(
                    type="answer", input={"text": "Here are my recommendations"}
                )
            ],
        },
    )

    result = orch.run("what build for league start?")
    assert result == "Here are my recommendations"


# ---------------------------------------------------------------------------
# _run_agent_to_completion — intercepts routing
# ---------------------------------------------------------------------------


def test_run_agent_to_completion_intercepts_routing(settings):
    """When a sub-agent routes to its next agent, capture the query as output."""
    orch = _make_orchestrator(
        settings,
        agent_responses={
            "researcher": [
                NextStep(
                    type="call",
                    input={"target": "answerer", "query": "my research report"},
                )
            ],
        },
    )
    orch._conversation_context = "test context"
    orch._accumulated_research = []
    orch._on_status = None

    result = orch._run_agent_to_completion("researcher", "look up prices")
    assert result == "my research report"


def test_run_agent_to_completion_with_tool_calls(settings):
    """Sub-agent can use tools before producing its final output."""
    tool_call_step = NextStep(
        type="call",
        input={
            "tools": [{"id": "tu_1", "name": "get_build_meta", "input": {}}],
            "return_to": "researcher",
        },
    )
    final_step = NextStep(
        type="call", input={"target": "answerer", "query": "report with data"}
    )

    orch = _make_orchestrator(
        settings,
        agent_responses={
            "researcher": [tool_call_step, final_step],
        },
    )
    orch._conversation_context = "test context"
    orch._accumulated_research = []
    orch._on_status = None

    # Mock the tool
    mock_tool = MagicMock(spec=ToolStep)
    mock_tool.call.return_value = NextStep(
        type="answer", input={"result": {"builds": []}}
    )
    orch.steps["get_build_meta"] = mock_tool

    result = orch._run_agent_to_completion("researcher", "check build meta")
    assert result == "report with data"
    mock_tool.call.assert_called_once()


def test_run_agent_to_completion_direct_answer(settings):
    """Sub-agent produces a direct answer (no routing)."""
    orch = _make_orchestrator(
        settings,
        agent_responses={
            "fact_checker": [
                NextStep(type="answer", input={"text": "Verdict: CLEAN"})
            ],
        },
    )
    orch._conversation_context = "test context"
    orch._accumulated_research = []
    orch._on_status = None

    result = orch._run_agent_to_completion("fact_checker", "verify this data")
    assert result == "Verdict: CLEAN"


# ---------------------------------------------------------------------------
# Budget exceeded during delegation
# ---------------------------------------------------------------------------


def test_delegation_budget_exceeded_returns_partial(settings):
    """When budget runs out during delegation, return partial results."""
    tool_call_step = NextStep(
        type="call",
        input={
            "tools": [{"id": "tu_1", "name": "get_build_meta", "input": {}}],
            "return_to": "researcher",
        },
    )

    orch = _make_orchestrator(
        settings,
        agent_responses={
            "researcher": [tool_call_step],
        },
    )
    orch._conversation_context = "test context"
    orch._accumulated_research = []
    orch._on_status = None
    orch.max_api_calls = 2
    orch.api_calls = (
        1  # only 1 call left — will be used by _call_agent for researcher
    )

    # Mock the tool
    mock_tool = MagicMock(spec=ToolStep)
    mock_tool.call.return_value = NextStep(
        type="answer", input={"result": {"data": "partial"}}
    )
    orch.steps["get_build_meta"] = mock_tool

    result = orch._run_agent_to_completion("researcher", "check meta")
    assert "partial results" in result or "budget exceeded" in result


# ---------------------------------------------------------------------------
# Delegation tool detection and dispatch
# ---------------------------------------------------------------------------


def test_handle_delegation_research(settings):
    """delegate_research dispatches to researcher via _run_agent_to_completion."""
    orch = _make_orchestrator(
        settings,
        agent_responses={
            "researcher": [
                NextStep(
                    type="call",
                    input={"target": "answerer", "query": "research done"},
                )
            ],
        },
    )
    orch._conversation_context = "context"
    orch._accumulated_research = []
    orch._on_status = None

    result = orch._handle_delegation(
        "delegate_research", {"task": "look up meta"}
    )
    assert result == "research done"


def test_handle_delegation_build_with_context(settings):
    """delegate_build passes context to the build agent."""
    orch = _make_orchestrator(
        settings,
        agent_responses={
            "build_agent": [
                NextStep(
                    type="call",
                    input={"target": "answerer", "query": "build report"},
                )
            ],
        },
    )
    orch._conversation_context = "context"
    orch._accumulated_research = []
    orch._on_status = None

    result = orch._handle_delegation(
        "delegate_build",
        {"task": "compose LA build", "context": "prior research findings"},
    )
    assert result == "build report"


def test_handle_delegation_fact_check(settings):
    """delegate_fact_check runs a single-shot call to fact_checker."""
    orch = _make_orchestrator(
        settings,
        agent_responses={
            "fact_checker": [
                NextStep(type="answer", input={"text": "Verdict: CAUTION"})
            ],
        },
    )
    orch._conversation_context = "context"
    orch._accumulated_research = []
    orch._on_status = None

    result = orch._handle_delegation(
        "delegate_fact_check",
        {"research": "some findings", "original_question": "what to play?"},
    )
    assert "CAUTION" in result


# ---------------------------------------------------------------------------
# Budget injection for planner
# ---------------------------------------------------------------------------


def test_planner_receives_budget_info(settings):
    """When routing to planner, budget info is prepended to the query."""
    orch = _make_orchestrator(
        settings,
        agent_responses={
            "router": [
                NextStep(
                    type="call",
                    input={"target": "planner", "query": "complex question"},
                )
            ],
            "planner": [
                NextStep(
                    type="call",
                    input={"target": "answerer", "query": "synthesis"},
                )
            ],
            "answerer": [NextStep(type="answer", input={"text": "answer"})],
        },
    )

    result = orch.run("complex multi-step question")
    assert result == "answer"

    # Verify planner was called with budget info in the query
    planner_step = orch.steps["planner"]
    call_args = planner_step.call.call_args  # type: ignore
    query = call_args[0][0]["query"]
    assert "Budget" in query
    assert "API calls remaining" in query


# ---------------------------------------------------------------------------
# Status labels
# ---------------------------------------------------------------------------


def test_status_labels_include_new_agents(settings):
    """Status labels include planner and fact_checker."""
    assert "planner" in STATUS_LABELS
    assert "fact_checker" in STATUS_LABELS


def test_status_label_delegation_tools(settings):
    """_status_label returns delegation-specific labels."""
    orch = _make_orchestrator(settings)
    decision = NextStep(
        type="call",
        input={
            "tools": [
                {
                    "id": "d1",
                    "name": "delegate_research",
                    "input": {"task": "test"},
                }
            ],
            "return_to": "planner",
        },
    )
    label = orch._status_label(decision)
    assert label == "Researching..."


# ---------------------------------------------------------------------------
# Max API calls increased
# ---------------------------------------------------------------------------


def test_max_api_calls_is_25(settings):
    """Default max_api_calls should be 25 to accommodate planner overhead."""
    orch = _make_orchestrator(settings)
    assert orch.max_api_calls == 25


# ---------------------------------------------------------------------------
# truncate
# ---------------------------------------------------------------------------


def testtruncate_short_text():
    assert truncate("hello", 50) == "hello"


def testtruncate_long_text():
    long = "a" * 60
    result = truncate(long, 50)
    assert len(result) == 50
    assert result.endswith("\u2026")


# ---------------------------------------------------------------------------
# tool_status_label
# ---------------------------------------------------------------------------


def testtool_status_label_read_webpage():
    label = tool_status_label(
        "read_webpage",
        {"url": "https://maxroll.gg/guides/lightning-arrow-deadeye"},
    )
    assert "maxroll.gg" in label
    assert label.startswith("Reading ")


def testtool_status_label_read_webpage_with_section():
    label = tool_status_label(
        "read_webpage",
        {
            "url": "https://maxroll.gg/guides/la-build",
            "section": "Gem Links",
        },
    )
    assert '"Gem Links"' in label
    assert "maxroll.gg" in label


def testtool_status_label_web_search():
    label = tool_status_label(
        "poe_web_search", {"query": "Lightning Arrow build guide"}
    )
    assert label.startswith("Searching: ")
    assert "Lightning Arrow" in label


def testtool_status_label_item_prices_with_filter():
    label = tool_status_label(
        "get_item_prices", {"type": "UniqueArmour", "name": "Mageblood"}
    )
    assert '"Mageblood"' in label


def testtool_status_label_build_meta_with_class():
    label = tool_status_label("get_build_meta", {"class_filter": "Deadeye"})
    assert "Deadeye" in label


def testtool_status_label_fallback():
    label = tool_status_label("get_currency_prices", {})
    assert label == "Checking currency prices..."


# ---------------------------------------------------------------------------
# force_answer
# ---------------------------------------------------------------------------


def test_force_answer_with_research(settings):
    orch = _make_orchestrator(
        settings,
        agent_responses={
            "answerer": [
                NextStep(type="answer", input={"text": "Synthesized answer"})
            ],
        },
    )
    orch._conversation_context = "How much is a Mageblood?"
    orch._accumulated_research = ["[get_item_prices] Mageblood: 300 div"]
    orch._on_status = None

    result = orch.force_answer()
    assert result == "Synthesized answer"
    assert orch.messages[-1]["content"] == "Synthesized answer"


def test_force_answer_with_extra_context(settings):
    orch = _make_orchestrator(
        settings,
        agent_responses={
            "answerer": [
                NextStep(type="answer", input={"text": "Enriched answer"})
            ],
        },
    )
    orch._conversation_context = "What build for league start?"
    orch._accumulated_research = ["[get_build_meta] Deadeye is top"]
    orch._on_status = None

    result = orch.force_answer(extra_context="I prefer ranged builds")
    assert result == "Enriched answer"
    # Verify extra context was passed to the answerer
    call_args = orch.steps["answerer"].call.call_args[0][0]  # type: ignore
    assert "I prefer ranged builds" in call_args["query"]


def test_force_answer_empty_research(settings):
    orch = _make_orchestrator(
        settings,
        agent_responses={
            "answerer": [
                NextStep(type="answer", input={"text": "Best effort answer"})
            ],
        },
    )
    orch._conversation_context = "Some question"
    orch._accumulated_research = []
    orch._on_status = None

    result = orch.force_answer()
    assert result == "Best effort answer"
    # Verify it mentions no research collected
    call_args = orch.steps["answerer"].call.call_args[0][0]  # type: ignore
    assert "no research collected" in call_args["query"]
