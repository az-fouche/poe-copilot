"""LLM backend protocol and shared response types.

Defines the ``LLMBackend`` protocol that all provider implementations
must satisfy, plus the portable content-block types returned by
``LLMBackend.complete``.
"""

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class ToolUseBlock:
    """A tool-use request returned by an LLM.

    Attributes
    ----------
    id : str
        Unique identifier for this tool invocation.
    name : str
        Name of the tool the model wants to call.
    input : dict[str, Any]
        Arguments the model passed to the tool.
    """

    id: str
    name: str
    input: dict[str, Any]


ContentBlock = str | ToolUseBlock


class LLMBackend(Protocol):
    """Protocol every LLM provider backend must implement."""

    def complete(
        self,
        *,
        model: str,
        max_tokens: int,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> list[ContentBlock]:
        """Send a chat-completion request and return content blocks.

        Parameters
        ----------
        model : str
            Model identifier (e.g. ``"claude-sonnet-4-20250514"``).
        max_tokens : int
            Maximum number of tokens to generate.
        system : str
            System prompt prepended to the conversation.
        messages : list[dict[str, Any]]
            Conversation history in OpenAI-style message dicts.
        tools : list[dict[str, Any]] or None, optional
            Tool definitions.  ``None`` disables tool use.

        Returns
        -------
        list[ContentBlock]
            Ordered content blocks (text strings and/or
            ``ToolUseBlock`` instances).
        """
        ...
