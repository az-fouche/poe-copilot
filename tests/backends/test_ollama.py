"""Tests for poe_copilot/backends/ollama.py."""

import json
from unittest.mock import MagicMock, patch

import httpx
import pytest

from poe_copilot.backends.backend import ToolUseBlock
from poe_copilot.backends.ollama import (
    OllamaBackend,
    _translate_messages,
    _translate_tools,
    list_models,
)


# ── list_models ──────────────────────────────────────────────────────


@patch("poe_copilot.backends.ollama.httpx.get")
def test_list_models_returns_sorted_names(mock_get):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "models": [
            {"name": "qwen2.5:14b", "size": 100},
            {"name": "llama3:8b", "size": 200},
        ]
    }
    mock_get.return_value = mock_resp
    result = list_models("http://localhost:11434")
    assert result == ["llama3:8b", "qwen2.5:14b"]
    mock_get.assert_called_once_with(
        "http://localhost:11434/api/tags", timeout=5.0
    )


@patch("poe_copilot.backends.ollama.httpx.get")
def test_list_models_connection_error_returns_empty(mock_get):
    mock_get.side_effect = httpx.ConnectError("refused")
    assert list_models("http://localhost:11434") == []


@patch("poe_copilot.backends.ollama.httpx.get")
def test_list_models_empty_response_returns_empty(mock_get):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"models": []}
    mock_get.return_value = mock_resp
    assert list_models("http://localhost:11434") == []


@patch("poe_copilot.backends.ollama.httpx.get")
def test_list_models_strips_trailing_slash(mock_get):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"models": [{"name": "m1"}]}
    mock_get.return_value = mock_resp
    list_models("http://localhost:11434/")
    mock_get.assert_called_once_with(
        "http://localhost:11434/api/tags", timeout=5.0
    )


# ── _translate_tools ─────────────────────────────────────────────────


def test_translate_tools_converts_input_schema_to_parameters():
    anthropic_tools = [
        {
            "name": "get_price",
            "description": "Get item price",
            "input_schema": {
                "type": "object",
                "properties": {"item": {"type": "string"}},
                "required": ["item"],
            },
        }
    ]
    result = _translate_tools(anthropic_tools)
    assert result == [
        {
            "type": "function",
            "function": {
                "name": "get_price",
                "description": "Get item price",
                "parameters": {
                    "type": "object",
                    "properties": {"item": {"type": "string"}},
                    "required": ["item"],
                },
            },
        }
    ]


def test_translate_tools_handles_missing_optional_fields():
    result = _translate_tools([{"name": "noop"}])
    func = result[0]["function"]
    assert func["name"] == "noop"
    assert func["description"] == ""
    assert func["parameters"] == {}


# ── _translate_messages ──────────────────────────────────────────────


def test_translate_plain_user_message():
    msgs = [{"role": "user", "content": "hello"}]
    assert _translate_messages(msgs) == [{"role": "user", "content": "hello"}]


def test_translate_assistant_with_tool_use_blocks():
    msgs = [
        {
            "role": "assistant",
            "content": [
                "thinking...",
                ToolUseBlock(
                    id="t1",
                    name="search",
                    input={"q": "test"},
                ),
            ],
        }
    ]
    result = _translate_messages(msgs)
    assert result[0]["role"] == "assistant"
    assert result[0]["content"] == "thinking..."
    assert len(result[0]["tool_calls"]) == 1
    tc = result[0]["tool_calls"][0]
    assert tc["id"] == "t1"
    assert tc["function"]["name"] == "search"
    assert json.loads(tc["function"]["arguments"]) == {"q": "test"}


def test_translate_tool_results():
    msgs = [
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "t1",
                    "content": "price is 50c",
                }
            ],
        }
    ]
    result = _translate_messages(msgs)
    assert result[0] == {
        "role": "tool",
        "tool_call_id": "t1",
        "content": "price is 50c",
    }


def test_translate_tool_results_with_content_blocks():
    msgs = [
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "t1",
                    "content": [
                        {"type": "text", "text": "line1"},
                        {"type": "text", "text": "line2"},
                    ],
                }
            ],
        }
    ]
    result = _translate_messages(msgs)
    assert result[0]["content"] == "line1\nline2"


# ── OllamaBackend.complete ──────────────────────────────────────────


def _make_backend(
    base_url: str = "http://localhost:11434",
    model: str = "qwen2.5:14b",
) -> OllamaBackend:
    return OllamaBackend(base_url=base_url, model_override=model)


def _mock_response(
    content: str | None = None,
    tool_calls: list | None = None,
    status_code: int = 200,
) -> MagicMock:
    """Build a mock httpx.Response."""
    msg: dict = {}
    if content is not None:
        msg["content"] = content
    if tool_calls is not None:
        msg["tool_calls"] = tool_calls
    body = {"choices": [{"message": msg}]}

    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = body
    return resp


def test_complete_text_response():
    backend = _make_backend()
    resp = _mock_response(content="Hello exile")

    with patch.object(backend._client, "post", return_value=resp):
        blocks = backend.complete(
            model="ignored",
            max_tokens=100,
            system="You are helpful.",
            messages=[{"role": "user", "content": "hi"}],
        )

    assert blocks == ["Hello exile"]


def test_complete_tool_call_response():
    backend = _make_backend()
    resp = _mock_response(
        tool_calls=[
            {
                "id": "call_abc",
                "function": {
                    "name": "get_price",
                    "arguments": '{"item": "Divine Orb"}',
                },
            }
        ]
    )

    with patch.object(backend._client, "post", return_value=resp):
        blocks = backend.complete(
            model="ignored",
            max_tokens=100,
            system="sys",
            messages=[{"role": "user", "content": "price?"}],
        )

    assert len(blocks) == 1
    assert isinstance(blocks[0], ToolUseBlock)
    assert blocks[0].id == "call_abc"
    assert blocks[0].name == "get_price"
    assert blocks[0].input == {"item": "Divine Orb"}


def test_complete_uses_model_override():
    backend = _make_backend(model="llama3:8b")
    resp = _mock_response(content="ok")

    with patch.object(backend._client, "post", return_value=resp) as mock_post:
        backend.complete(
            model="claude-sonnet-4-20250514",
            max_tokens=100,
            system="sys",
            messages=[{"role": "user", "content": "hi"}],
        )

    payload = mock_post.call_args[1]["json"]
    assert payload["model"] == "llama3:8b"


def test_complete_connection_error():
    backend = _make_backend()

    with patch.object(
        backend._client,
        "post",
        side_effect=httpx.ConnectError("refused"),
    ):
        with pytest.raises(ConnectionError, match="is it running"):
            backend.complete(
                model="x",
                max_tokens=1,
                system="",
                messages=[],
            )


def test_complete_404_model_not_found():
    backend = _make_backend(model="nonexistent:7b")
    resp = _mock_response(status_code=404)

    with patch.object(backend._client, "post", return_value=resp):
        with pytest.raises(RuntimeError, match="ollama pull"):
            backend.complete(
                model="x",
                max_tokens=1,
                system="",
                messages=[],
            )


def test_complete_generates_fallback_id_when_missing():
    backend = _make_backend()
    resp = _mock_response(
        tool_calls=[
            {
                "function": {
                    "name": "search",
                    "arguments": "{}",
                },
            }
        ]
    )

    with patch.object(backend._client, "post", return_value=resp):
        blocks = backend.complete(
            model="x",
            max_tokens=1,
            system="",
            messages=[{"role": "user", "content": "hi"}],
        )

    assert isinstance(blocks[0], ToolUseBlock)
    assert blocks[0].id.startswith("call_")


def test_complete_handles_arguments_as_dict():
    backend = _make_backend()
    resp = _mock_response(
        tool_calls=[
            {
                "id": "c1",
                "function": {
                    "name": "search",
                    "arguments": {"q": "test"},
                },
            }
        ]
    )

    with patch.object(backend._client, "post", return_value=resp):
        blocks = backend.complete(
            model="x",
            max_tokens=1,
            system="",
            messages=[{"role": "user", "content": "hi"}],
        )

    assert blocks[0].input == {"q": "test"}


def test_complete_passes_tools_in_payload():
    backend = _make_backend()
    resp = _mock_response(content="ok")
    tools = [
        {
            "name": "t1",
            "description": "d",
            "input_schema": {"type": "object"},
        }
    ]

    with patch.object(backend._client, "post", return_value=resp) as mock_post:
        backend.complete(
            model="x",
            max_tokens=100,
            system="sys",
            messages=[{"role": "user", "content": "hi"}],
            tools=tools,
        )

    payload = mock_post.call_args[1]["json"]
    assert "tools" in payload
    assert payload["tools"][0]["type"] == "function"
