"""Ollama local LLM backend implementation.

Wraps Ollama's OpenAI-compatible API behind the :class:`LLMBackend`
protocol, translating between Anthropic-style tool/message formats
(used internally by AgentStep) and OpenAI-style formats.
"""

import json
import logging
import uuid
from typing import Any

import httpx

from .backend import ContentBlock, ToolUseBlock

logger = logging.getLogger(__name__)

_TIMEOUT = 120.0  # local inference is slow


def _translate_tools(
    tools: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Convert Anthropic tool defs to OpenAI function-calling format."""
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("input_schema", {}),
            },
        }
        for t in tools
    ]


def _translate_messages(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Convert internal message thread to OpenAI chat format.

    Handles three shapes: plain text, assistant with ToolUseBlock
    content, and user-side tool results.
    """
    out: list[dict[str, Any]] = []
    for msg in messages:
        role = msg["role"]
        content = msg["content"]

        # Assistant with content blocks (may contain ToolUseBlock)
        if role == "assistant" and isinstance(content, list):
            text_parts: list[str] = []
            tool_calls: list[dict[str, Any]] = []
            for block in content:
                if isinstance(block, str):
                    text_parts.append(block)
                elif isinstance(block, ToolUseBlock):
                    tool_calls.append(
                        {
                            "id": block.id,
                            "type": "function",
                            "function": {
                                "name": block.name,
                                "arguments": json.dumps(block.input),
                            },
                        }
                    )
            entry: dict[str, Any] = {
                "role": "assistant",
                "content": "\n".join(text_parts) or None,
            }
            if tool_calls:
                entry["tool_calls"] = tool_calls
            out.append(entry)
            continue

        # User with tool results (Anthropic format)
        if (
            role == "user"
            and isinstance(content, list)
            and content
            and content[0].get("type") == "tool_result"
        ):
            for result in content:
                rc = result.get("content", "")
                if isinstance(rc, list):
                    rc = "\n".join(
                        b.get("text", "") for b in rc if isinstance(b, dict)
                    )
                out.append(
                    {
                        "role": "tool",
                        "tool_call_id": result["tool_use_id"],
                        "content": str(rc),
                    }
                )
            continue

        # Plain text — pass through
        out.append({"role": role, "content": content})

    return out


class OllamaBackend:
    """LLM backend backed by a local Ollama server.

    Parameters
    ----------
    base_url : str
        Ollama server URL (e.g. ``"http://localhost:11434"``).
    model_override : str
        Single model name used for all agents.
    """

    def __init__(self, base_url: str, model_override: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model_override
        self._client = httpx.Client(timeout=_TIMEOUT)

    def complete(
        self,
        *,
        model: str,
        max_tokens: int,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> list[ContentBlock]:
        """Send a completion request to the Ollama server.

        Parameters
        ----------
        model : str
            Ignored — *model_override* is used instead.
        max_tokens : int
            Maximum tokens to generate.
        system : str
            System prompt.
        messages : list[dict[str, Any]]
            Conversation history in internal format.
        tools : list[dict[str, Any]] or None, optional
            Tool definitions in Anthropic format.

        Returns
        -------
        list[ContentBlock]
            Portable content blocks.
        """
        wire = [
            {"role": "system", "content": system},
            *_translate_messages(messages),
        ]

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": wire,
            "stream": False,
            "options": {"num_predict": max_tokens},
        }
        if tools:
            payload["tools"] = _translate_tools(tools)

        url = f"{self._base_url}/v1/chat/completions"
        try:
            resp = self._client.post(url, json=payload)
        except httpx.ConnectError:
            raise ConnectionError(
                f"Cannot connect to Ollama at {self._base_url}"
                " — is it running? Start with: ollama serve"
            ) from None

        if resp.status_code == 404:
            raise RuntimeError(
                f"Model '{self._model}' not found. "
                f"Pull it first: ollama pull {self._model}"
            )
        resp.raise_for_status()

        data = resp.json()
        msg = data["choices"][0]["message"]

        blocks: list[ContentBlock] = []
        if msg.get("content"):
            blocks.append(msg["content"])

        for tc in msg.get("tool_calls", []):
            func = tc["function"]
            call_id = tc.get("id") or f"call_{uuid.uuid4().hex[:8]}"
            args = func.get("arguments", "{}")
            if isinstance(args, str):
                args = json.loads(args)
            blocks.append(
                ToolUseBlock(id=call_id, name=func["name"], input=args)
            )

        return blocks
