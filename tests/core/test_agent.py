"""Tests for poe_copilot/agent.py — 14 tests."""

from unittest.mock import MagicMock

# Import helpers from conftest
from conftest import make_text_response, make_tool_response

from poe_copilot.core.agent import AgentStep, ToolStep

# ── AgentStep.call — query input ──────────────────────────────────────────


def test_call_with_query_sets_thread(mock_anthropic_client):
    resp = make_text_response("hello")
    client = mock_anthropic_client(responses=[resp])
    agent = AgentStep(
        name="test",
        primer="system prompt",
        model="claude-haiku-4-5-20251001",
        client=client,
    )
    agent.call({"query": "test"})
    assert len(agent._thread) == 2
    assert agent._thread[0] == {"role": "user", "content": "test"}
    assert agent._thread[1]["role"] == "assistant"
    assert agent._thread[1]["content"] is resp.content


def test_call_returns_tool_calls(mock_anthropic_client):
    resp = make_tool_response(
        [
            {
                "id": "tu_1",
                "name": "get_currency_prices",
                "input": {"type": "Currency"},
            },
            {"id": "tu_2", "name": "poe_web_search", "input": {"query": "test"}},
        ]
    )
    client = mock_anthropic_client(responses=[resp])
    agent = AgentStep(
        name="researcher",
        primer="prompt",
        model="claude-haiku-4-5-20251001",
        tools=[{"name": "get_currency_prices"}],
        client=client,
    )
    result = agent.call({"query": "check prices"})
    assert result.type == "call"
    assert len(result.input["tools"]) == 2
    assert result.input["tools"][0]["id"] == "tu_1"
    assert result.input["tools"][1]["id"] == "tu_2"
    assert result.input["return_to"] == "researcher"


def test_call_with_tools_includes_tools_in_kwargs(mock_anthropic_client):
    resp = make_text_response("ok")
    client = mock_anthropic_client(responses=[resp])
    tools_defs = [{"name": "test_tool"}]
    agent = AgentStep(
        name="test",
        primer="prompt",
        model="claude-haiku-4-5-20251001",
        tools=tools_defs,
        client=client,
    )
    agent.call({"query": "hi"})
    kwargs = client.messages.create.call_args[1]
    assert "tools" in kwargs
    assert kwargs["tools"] is tools_defs


def test_call_without_tools_omits_tools_kwarg(mock_anthropic_client):
    resp = make_text_response("ok")
    client = mock_anthropic_client(responses=[resp])
    agent = AgentStep(
        name="test",
        primer="prompt",
        model="claude-haiku-4-5-20251001",
        tools=None,
        client=client,
    )
    agent.call({"query": "hi"})
    kwargs = client.messages.create.call_args[1]
    assert "tools" not in kwargs


# ── AgentStep.call — tool_results input ───────────────────────────────────


def test_call_with_tool_results_appends_to_thread(mock_anthropic_client):
    resp1 = make_tool_response(
        [
            {"id": "tu_1", "name": "t", "input": {}},
        ]
    )
    resp2 = make_text_response("done")
    client = mock_anthropic_client(responses=[resp1, resp2])
    agent = AgentStep(
        name="researcher",
        primer="prompt",
        model="claude-haiku-4-5-20251001",
        tools=[{"name": "t"}],
        client=client,
    )
    # First call with query
    agent.call({"query": "do stuff"})
    # Second call with tool results
    agent.call(
        {"tool_results": [{"tool_use_id": "tu_1", "content": "result data"}]}
    )
    assert len(agent._thread) == 4
    assert agent._thread[0]["role"] == "user"
    assert agent._thread[1]["role"] == "assistant"
    assert agent._thread[2]["role"] == "user"
    assert agent._thread[3]["role"] == "assistant"


# ── AgentStep._handle_decision_json ───────────────────────────────────────


def _make_agent_with_next(next_agent=None, client=None):
    if client is None:
        client = MagicMock()
    return AgentStep(
        name="router",
        primer="prompt",
        model="claude-haiku-4-5-20251001",
        next_agent=next_agent,
        client=client,
    )


def test_decision_json_clarify():
    agent = _make_agent_with_next(next_agent="researcher")
    text = '{"action":"clarify","clarifying_questions":[{"question":"Q?","options":["A","B"]}]}'
    result = agent._handle_decision_json(text)
    assert result.type == "answer"
    assert "clarification" in result.input
    assert result.input["clarification"]["action"] == "clarify"


def test_decision_json_route_to_target():
    agent = _make_agent_with_next()
    text = '{"target":"build_agent","query":"build plan"}'
    result = agent._handle_decision_json(text)
    assert result.type == "call"
    assert result.input["target"] == "build_agent"
    assert result.input["query"] == "build plan"


def test_decision_json_enriched_query_fallback():
    agent = _make_agent_with_next()
    text = '{"target":"researcher","enriched_query":"enriched"}'
    result = agent._handle_decision_json(text)
    assert result.input["query"] == "enriched"


def test_decision_json_no_target_uses_next_agent():
    agent = _make_agent_with_next(next_agent="answerer")
    text = '{"response":"some text"}'
    result = agent._handle_decision_json(text)
    assert result.type == "call"
    assert result.input["target"] == "answerer"


def test_decision_json_invalid_json_with_next_agent():
    agent = _make_agent_with_next(next_agent="answerer")
    text = "not json at all"
    result = agent._handle_decision_json(text)
    assert result.type == "call"
    assert result.input["target"] == "answerer"
    assert result.input["query"] == "not json at all"


def test_decision_json_invalid_json_no_next_agent():
    agent = _make_agent_with_next(next_agent=None)
    text = "plain text answer"
    result = agent._handle_decision_json(text)
    assert result.type == "answer"
    assert result.input["text"] == "plain text answer"


def test_decision_json_strips_markdown_fences():
    agent = _make_agent_with_next()
    text = '```json\n{"target":"researcher","query":"q"}\n```'
    result = agent._handle_decision_json(text)
    assert result.type == "call"
    assert result.input["target"] == "researcher"
    assert result.input["query"] == "q"


# ── ToolStep ──────────────────────────────────────────────────────────────


def test_toolstep_handler_exception():
    def boom(name, input, settings):
        raise ValueError("boom")

    step = ToolStep(name="test_tool", handler=boom, settings={})
    result = step.call({"query": "x"})
    assert result.type == "answer"
    assert result.input["result"] == {"error": "boom"}
