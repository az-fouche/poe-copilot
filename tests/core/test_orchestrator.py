"""Tests for the 3-agent pipeline: Router → Analyst → Answerer."""

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
        "analyst": {
            "model": "m",
            "tools": True,
            "next": "answerer",
            "max_tokens": 4096,
        },
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
            "poe_copilot.core.orchestrator.build_primer",
            return_value="primer",
        ),
    ):
        mock_reg.return_value = _MOCK_REGISTRY
        orch = Orchestrator(settings, backend=MagicMock())

    # Replace agent steps with mocks
    for name, responses in agent_responses.items():
        mock_step = MagicMock(spec=AgentStep)
        mock_step.name = name
        mock_step.reset = MagicMock()
        mock_step.call = MagicMock(side_effect=responses)
        mock_step._thread = []
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
    orch.messages.append({"role": "user", "content": "current"})
    result = orch._build_context("current")
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
    orch.messages = [{"role": "user", "content": f"msg{i}"} for i in range(10)]
    orch.messages.append({"role": "user", "content": "current"})
    result = orch._build_context("current")
    assert "msg4" in result
    assert "msg9" in result
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


def test_run_router_to_analyst_to_answerer(settings):
    """Standard flow: router → analyst → answerer."""
    orch = _make_orchestrator(
        settings,
        agent_responses={
            "router": [
                NextStep(
                    type="call",
                    input={"target": "analyst", "query": "q"},
                )
            ],
            "analyst": [
                NextStep(
                    type="call",
                    input={
                        "target": "answerer",
                        "query": "research done",
                    },
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


def test_run_level1_router_to_answerer_direct(settings):
    """Trivial routing: chitchat goes directly to answerer."""
    orch = _make_orchestrator(
        settings,
        agent_responses={
            "router": [
                NextStep(
                    type="call",
                    input={
                        "target": "answerer",
                        "query": "Just a greeting",
                    },
                )
            ],
            "answerer": [
                NextStep(
                    type="answer",
                    input={"text": "Hey there, exile!"},
                )
            ],
        },
    )
    result = orch.run("hi")
    assert result == "Hey there, exile!"
    # Analyst should not have been called
    analyst = orch.steps.get("analyst")
    if isinstance(analyst, MagicMock):
        assert not analyst.call.called


def test_run_clarification_flow(settings):
    clarify_data = {
        "action": "clarify",
        "clarifying_questions": [{"question": "Q?", "options": ["A", "B"]}],
    }
    orch = _make_orchestrator(
        settings,
        agent_responses={
            "router": [
                NextStep(
                    type="answer",
                    input={"clarification": clarify_data},
                )
            ],
        },
    )
    result = orch.run("hello")
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0].question == "Q?"
    assert len(orch.messages) == 0


def test_run_tool_execution_loop(settings):
    """Analyst uses tools, gets results, then routes to answerer."""
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
            "return_to": "analyst",
        },
    )
    after_tool_step = NextStep(
        type="call",
        input={"target": "answerer", "query": "done"},
    )

    orch = _make_orchestrator(
        settings,
        agent_responses={
            "router": [
                NextStep(
                    type="call",
                    input={"target": "analyst", "query": "q"},
                )
            ],
            "analyst": [tool_call_step, after_tool_step],
            "answerer": [NextStep(type="answer", input={"text": "final"})],
        },
    )

    mock_tool = MagicMock(spec=ToolStep)
    mock_tool.call.return_value = NextStep(
        type="answer", input={"result": {"prices": []}}
    )
    orch.steps["get_currency_prices"] = mock_tool

    result = orch.run("check prices")
    assert result == "final"
    mock_tool.call.assert_called_once_with({"type": "Currency"})


def test_run_analyst_multi_turn_tool_use(settings):
    """Analyst makes multiple tool calls across turns."""
    first_tool = NextStep(
        type="call",
        input={
            "tools": [{"id": "tu_1", "name": "get_build_meta", "input": {}}],
            "return_to": "analyst",
        },
    )
    second_tool = NextStep(
        type="call",
        input={
            "tools": [
                {
                    "id": "tu_2",
                    "name": "poe_web_search",
                    "input": {"query": "LA build guide"},
                }
            ],
            "return_to": "analyst",
        },
    )
    final = NextStep(
        type="call",
        input={"target": "answerer", "query": "report"},
    )

    orch = _make_orchestrator(
        settings,
        agent_responses={
            "router": [
                NextStep(
                    type="call",
                    input={"target": "analyst", "query": "q"},
                )
            ],
            "analyst": [first_tool, second_tool, final],
            "answerer": [
                NextStep(
                    type="answer",
                    input={"text": "build advice here"},
                )
            ],
        },
    )

    mock_meta = MagicMock(spec=ToolStep)
    mock_meta.call.return_value = NextStep(
        type="answer", input={"result": {"builds": []}}
    )
    mock_search = MagicMock(spec=ToolStep)
    mock_search.call.return_value = NextStep(
        type="answer", input={"result": {"results": []}}
    )
    orch.steps["get_build_meta"] = mock_meta
    orch.steps["poe_web_search"] = mock_search

    result = orch.run("what build for league start?")
    assert result == "build advice here"
    mock_meta.call.assert_called_once()
    mock_search.call.assert_called_once()


def test_run_api_cap_forces_answerer(settings):
    orch = _make_orchestrator(
        settings,
        agent_responses={
            "router": [
                NextStep(
                    type="call",
                    input={"target": "analyst", "query": "q"},
                )
            ],
            "analyst": [
                NextStep(
                    type="call",
                    input={"target": "answerer", "query": "done"},
                )
            ],
            "answerer": [
                NextStep(
                    type="answer",
                    input={"text": "forced answer"},
                )
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
                    type="call",
                    input={"target": "analyst", "query": "q"},
                )
            ],
        },
    )
    orch.max_api_calls = 1
    mock_answerer = MagicMock(spec=AgentStep)
    mock_answerer.name = "answerer"
    mock_answerer.reset = MagicMock()
    mock_answerer.call = MagicMock(
        return_value=NextStep(
            type="call",
            input={"target": "analyst", "query": "loop"},
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
    assert orch.api_calls == 1
    for step in orch.steps.values():
        if isinstance(step, MagicMock) and hasattr(step, "reset"):
            assert step.reset.call_count >= 1


def test_run_answerer_requests_more_research(settings):
    """Answerer can route back to analyst for more research."""
    orch = _make_orchestrator(
        settings,
        agent_responses={
            "router": [
                NextStep(
                    type="call",
                    input={"target": "analyst", "query": "q"},
                )
            ],
            "analyst": [
                NextStep(
                    type="call",
                    input={
                        "target": "answerer",
                        "query": "initial report",
                    },
                ),
                # Second call after answerer requests more
                NextStep(
                    type="call",
                    input={
                        "target": "answerer",
                        "query": "deeper report",
                    },
                ),
            ],
            "answerer": [
                # First call: needs more research
                NextStep(
                    type="call",
                    input={
                        "target": "analyst",
                        "query": "need build details",
                    },
                ),
                # Second call: satisfied
                NextStep(
                    type="answer",
                    input={"text": "complete answer"},
                ),
            ],
        },
    )
    result = orch.run("recommend a build")
    assert result == "complete answer"


# ---------------------------------------------------------------------------
# Status labels
# ---------------------------------------------------------------------------


def test_status_labels_include_analyst(settings):
    """Status labels include analyst."""
    assert "analyst" in STATUS_LABELS


def test_status_labels_exclude_old_agents(settings):
    """Old agent labels are removed."""
    assert "planner" not in STATUS_LABELS
    assert "researcher" not in STATUS_LABELS
    assert "build_agent" not in STATUS_LABELS
    assert "fact_checker" not in STATUS_LABELS
    assert "delegate_research" not in STATUS_LABELS


def test_status_label_for_tool_call(settings):
    """_status_label returns tool-specific labels."""
    orch = _make_orchestrator(settings)
    decision = NextStep(
        type="call",
        input={
            "tools": [{"id": "tu_1", "name": "get_build_meta", "input": {}}],
            "return_to": "analyst",
        },
    )
    label = orch._status_label(decision)
    assert label == "Checking build meta..."


# ---------------------------------------------------------------------------
# Max API calls
# ---------------------------------------------------------------------------


def test_max_api_calls_is_25(settings):
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
                NextStep(
                    type="answer",
                    input={"text": "Synthesized answer"},
                )
            ],
        },
    )
    orch._conversation_context = "How much is a Mageblood?"
    orch._on_status = None

    result = orch.force_answer()
    assert result == "Synthesized answer"
    assert orch.messages[-1]["content"] == "Synthesized answer"


def test_force_answer_with_extra_context(settings):
    orch = _make_orchestrator(
        settings,
        agent_responses={
            "answerer": [
                NextStep(
                    type="answer",
                    input={"text": "Enriched answer"},
                )
            ],
        },
    )
    orch._conversation_context = "What build for league start?"
    orch._on_status = None

    result = orch.force_answer(extra_context="I prefer ranged builds")
    assert result == "Enriched answer"
    call_args = orch.steps["answerer"].call.call_args[0][0]  # type: ignore
    assert "I prefer ranged builds" in call_args["query"]


def test_force_answer_empty_research(settings):
    orch = _make_orchestrator(
        settings,
        agent_responses={
            "answerer": [
                NextStep(
                    type="answer",
                    input={"text": "Best effort answer"},
                )
            ],
        },
    )
    orch._conversation_context = "Some question"
    orch._on_status = None

    result = orch.force_answer()
    assert result == "Best effort answer"
    call_args = orch.steps["answerer"].call.call_args[0][0]  # type: ignore
    assert "no research collected" in call_args["query"]


# ---------------------------------------------------------------------------
# Loadout injection
# ---------------------------------------------------------------------------


def test_loadout_injects_into_analyst_primer(settings):
    """Router sends loadout='builds' → analyst primer includes build content."""
    orch = _make_orchestrator(
        settings,
        agent_responses={
            "router": [
                NextStep(
                    type="call",
                    input={
                        "target": "analyst",
                        "query": "LA build",
                        "loadout": "builds",
                    },
                )
            ],
            "analyst": [
                NextStep(
                    type="call",
                    input={
                        "target": "answerer",
                        "query": "report",
                    },
                )
            ],
            "answerer": [NextStep(type="answer", input={"text": "done"})],
        },
    )
    # Replace analyst with a real AgentStep so primer mutation works
    analyst = AgentStep(
        name="analyst",
        primer="base primer",
        model="m",
        backend=MagicMock(),
        next_agent="answerer",
    )
    analyst.call = MagicMock(  # type: ignore
        return_value=NextStep(
            type="call",
            input={"target": "answerer", "query": "report"},
        )
    )
    orch.steps["analyst"] = analyst
    orch._analyst_base_primer = "base primer"

    orch.run("LA build guide")
    assert "Composition Framework" in analyst.primer


def test_no_loadout_uses_base_primer(settings):
    """No loadout field → analyst primer stays at base."""
    orch = _make_orchestrator(
        settings,
        agent_responses={
            "router": [
                NextStep(
                    type="call",
                    input={
                        "target": "analyst",
                        "query": "price check",
                    },
                )
            ],
            "analyst": [
                NextStep(
                    type="call",
                    input={
                        "target": "answerer",
                        "query": "report",
                    },
                )
            ],
            "answerer": [NextStep(type="answer", input={"text": "done"})],
        },
    )
    analyst = AgentStep(
        name="analyst",
        primer="base primer",
        model="m",
        backend=MagicMock(),
        next_agent="answerer",
    )
    analyst.call = MagicMock(  # type: ignore
        return_value=NextStep(
            type="call",
            input={"target": "answerer", "query": "report"},
        )
    )
    orch.steps["analyst"] = analyst
    orch._analyst_base_primer = "base primer"

    orch.run("how much is a divine?")
    assert analyst.primer == "base primer"


def test_unknown_loadout_falls_back_gracefully(settings):
    """Unknown loadout name → analyst primer stays at base."""
    orch = _make_orchestrator(
        settings,
        agent_responses={
            "router": [
                NextStep(
                    type="call",
                    input={
                        "target": "analyst",
                        "query": "q",
                        "loadout": "nonexistent",
                    },
                )
            ],
            "analyst": [
                NextStep(
                    type="call",
                    input={
                        "target": "answerer",
                        "query": "report",
                    },
                )
            ],
            "answerer": [NextStep(type="answer", input={"text": "done"})],
        },
    )
    analyst = AgentStep(
        name="analyst",
        primer="base primer",
        model="m",
        backend=MagicMock(),
        next_agent="answerer",
    )
    analyst.call = MagicMock(  # type: ignore
        return_value=NextStep(
            type="call",
            input={"target": "answerer", "query": "report"},
        )
    )
    orch.steps["analyst"] = analyst
    orch._analyst_base_primer = "base primer"

    orch.run("something")
    assert analyst.primer == "base primer"
