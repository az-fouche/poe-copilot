"""Tests for poe_agent/orchestrator.py — 12 tests."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from poe_agent.agent import AgentStep, NextStep, ToolStep
from poe_agent.orchestrator import (
    ClarificationRequest,
    ClarifyingQuestion,
    Orchestrator,
    _STATUS_LABELS,
)


# ---------------------------------------------------------------------------
# Helper: build a minimal Orchestrator with mocked dependencies
# ---------------------------------------------------------------------------

def _make_orchestrator(settings, agent_responses: dict[str, list] | None = None):
    """Create an Orchestrator with pre-wired mock agents.

    agent_responses maps agent name -> list of NextStep objects returned
    by successive calls.
    """
    agent_responses = agent_responses or {}

    with patch("poe_agent.orchestrator.load_registry") as mock_reg, \
         patch("poe_agent.orchestrator.build_primer", return_value="primer"), \
         patch("poe_agent.orchestrator.anthropic.Anthropic"):

        mock_reg.return_value = {
            "agents": {
                "router": {"model": "m", "tools": False, "next": "researcher", "output_format": "decision_json", "max_tokens": 1024},
                "researcher": {"model": "m", "tools": True, "next": "answerer", "max_tokens": 4096},
                "build_agent": {"model": "m", "tools": True, "next": "answerer", "max_tokens": 4096},
                "answerer": {"model": "m", "tools": False, "output_format": "decision_json", "max_tokens": 4096},
            },
            "tools": {},
        }
        orch = Orchestrator(settings)

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


def test_build_context_truncates_assistant_at_1500(settings):
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


def test_build_context_truncates_user_at_300(settings):
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
    orch = _make_orchestrator(settings, agent_responses={
        "router": [NextStep(type="call", input={"target": "researcher", "query": "q"})],
        "researcher": [NextStep(type="call", input={"target": "answerer", "query": "research done"})],
        "answerer": [NextStep(type="answer", input={"text": "final answer"})],
    })
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
    orch = _make_orchestrator(settings, agent_responses={
        "router": [NextStep(type="answer", input={"clarification": clarify_data})],
    })
    result = orch.run("hello")
    assert isinstance(result, ClarificationRequest)
    assert len(result.questions) == 1
    assert result.questions[0].question == "Q?"
    # User message should have been popped
    assert len(orch.messages) == 0


def test_run_tool_execution_loop(settings):
    tool_call_step = NextStep(type="call", input={
        "tools": [{"id": "tu_1", "name": "get_currency_prices", "input": {"type": "Currency"}}],
        "return_to": "researcher",
    })
    after_tool_step = NextStep(type="call", input={"target": "answerer", "query": "done"})

    orch = _make_orchestrator(settings, agent_responses={
        "router": [NextStep(type="call", input={"target": "researcher", "query": "q"})],
        "researcher": [tool_call_step, after_tool_step],
        "answerer": [NextStep(type="answer", input={"text": "final"})],
    })

    # Mock the tool step
    mock_tool = MagicMock(spec=ToolStep)
    mock_tool.call.return_value = NextStep(type="answer", input={"result": {"prices": []}})
    orch.steps["get_currency_prices"] = mock_tool

    result = orch.run("check prices")
    assert result == "final"
    mock_tool.call.assert_called_once_with({"type": "Currency"})


def test_run_api_cap_forces_answerer(settings):
    orch = _make_orchestrator(settings, agent_responses={
        "router": [NextStep(type="call", input={"target": "researcher", "query": "q"})],
        "researcher": [NextStep(type="call", input={"target": "answerer", "query": "done"})],
        "answerer": [NextStep(type="answer", input={"text": "forced answer"})],
    })
    orch.max_api_calls = 2
    result = orch.run("hello")
    assert result == "forced answer"


def test_run_circuit_breaker(settings):
    orch = _make_orchestrator(settings, agent_responses={
        "router": [NextStep(type="call", input={"target": "researcher", "query": "q"})],
    })
    orch.max_api_calls = 1
    # After router uses 1 call, next call hits the cap.
    # The forced answerer will return a non-answer type to trigger circuit breaker.
    mock_answerer = MagicMock(spec=AgentStep)
    mock_answerer.name = "answerer"
    mock_answerer.reset = MagicMock()
    mock_answerer.call = MagicMock(
        return_value=NextStep(type="call", input={"target": "researcher", "query": "loop"})
    )
    orch.steps["answerer"] = mock_answerer

    result = orch.run("hello")
    assert "I wasn't able to gather enough information" in result


def test_run_resets_agent_threads(settings):
    orch = _make_orchestrator(settings, agent_responses={
        "router": [
            NextStep(type="answer", input={"text": "first"}),
            NextStep(type="answer", input={"text": "second"}),
        ],
    })
    orch.run("first question")
    orch.run("second question")
    assert orch.api_calls == 1  # reset each run
    # Verify reset was called on agent steps
    for step in orch.steps.values():
        if isinstance(step, MagicMock) and hasattr(step, "reset"):
            assert step.reset.call_count >= 1
