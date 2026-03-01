"""Anthropic LLM backend implementation."""

from typing import Any

import anthropic

from .backend import ContentBlock, ToolUseBlock


def _serialize_content(content: Any) -> Any:
    """Convert assistant message content to Anthropic-compatible dicts.

    When AgentStep appends ``response.content`` (a list of our dataclasses)
    to the thread, subsequent API calls need those blocks as plain dicts so
    the Anthropic SDK can serialize them.
    """
    if not isinstance(content, list):
        return content

    out: list[Any] = []
    for block in content:
        if isinstance(block, str):
            out.append({"type": "text", "text": block})
        elif isinstance(block, ToolUseBlock):
            out.append(
                {
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                }
            )
        else:
            # Already a dict or native SDK object — pass through
            out.append(block)
    return out


class AnthropicBackend:
    """LLM backend backed by the Anthropic Messages API."""

    def __init__(self, client: anthropic.Anthropic) -> None:
        self._client = client

    def complete(
        self,
        *,
        model: str,
        max_tokens: int,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> list[ContentBlock]:
        wire_messages = [
            {**msg, "content": _serialize_content(msg["content"])}
            for msg in messages
        ]

        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "system": [
                {
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            "messages": wire_messages,
        }
        if tools:
            kwargs["tools"] = tools

        response = self._client.messages.create(**kwargs)

        blocks: list[ContentBlock] = []
        for block in response.content:
            if block.type == "text":
                blocks.append(block.text)
            elif block.type == "tool_use":
                blocks.append(
                    ToolUseBlock(
                        id=block.id,
                        name=block.name,
                        input=block.input,
                    )
                )

        return blocks
