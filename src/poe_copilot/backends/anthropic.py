"""Anthropic LLM backend implementation.

Wraps the Anthropic Messages API behind the :class:`LLMBackend` protocol
so the rest of the application stays provider-agnostic.
"""

from typing import Any

import anthropic

from .backend import ContentBlock, ToolUseBlock


def _serialize_content(content: Any) -> Any:
    """Convert assistant content blocks to Anthropic-compatible dicts.

    When ``AgentStep`` appends ``response.content`` (a list of our
    dataclasses) to the thread, subsequent API calls need those blocks
    as plain dicts so the Anthropic SDK can serialize them.

    Parameters
    ----------
    content : Any
        The ``content`` value from an assistant message dict.  May be a
        list of ``str`` / ``ToolUseBlock`` / raw dicts, or a non-list
        value that is returned unchanged.

    Returns
    -------
    Any
        A list of Anthropic-compatible dicts, or the original value
        when *content* is not a list.
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
    """LLM backend backed by the Anthropic Messages API.

    Parameters
    ----------
    client : anthropic.Anthropic
        Pre-configured Anthropic SDK client.
    """

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
        """Send a completion request via the Anthropic Messages API.

        Parameters
        ----------
        model : str
            Anthropic model identifier.
        max_tokens : int
            Maximum number of tokens to generate.
        system : str
            System prompt.
        messages : list[dict[str, Any]]
            Conversation history.
        tools : list[dict[str, Any]] or None, optional
            Tool definitions.  ``None`` disables tool use.

        Returns
        -------
        list[ContentBlock]
            Portable content blocks parsed from the API response.
        """
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
