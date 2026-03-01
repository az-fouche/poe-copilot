"""LLM backend protocol and shared response types."""

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class ToolUseBlock:
    id: str
    name: str
    input: dict[str, Any]


ContentBlock = str | ToolUseBlock


class LLMBackend(Protocol):
    def complete(
        self,
        *,
        model: str,
        max_tokens: int,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> list[ContentBlock]: ...
