import json

import anthropic

from .primer import build_system_prompt
from .tools import TOOL_DEFINITIONS, execute_tool


class PoeAgent:
    def __init__(
        self,
        settings: dict,
        model: str = "claude-sonnet-4-20250514",
    ):
        self.client = anthropic.Anthropic()
        self.model = model
        self.messages: list[dict] = []
        self.system_prompt = build_system_prompt(settings)

    def chat(self, user_message: str) -> str:
        self.messages.append({"role": "user", "content": user_message})

        # Agentic loop: keep going until we get a final text response
        while True:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=[
                    {
                        "type": "text",
                        "text": self.system_prompt,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                tools=TOOL_DEFINITIONS,
                messages=self.messages,
            )

            self.messages.append(
                {"role": "assistant", "content": response.content}
            )

            # Check for tool use
            tool_uses = [b for b in response.content if b.type == "tool_use"]

            if not tool_uses:
                # Final response — extract text
                text_parts = [
                    b.text for b in response.content if b.type == "text"
                ]
                return "\n".join(text_parts)

            # Execute each tool call and collect results
            tool_results = []
            for tool_use in tool_uses:
                result = execute_tool(tool_use.name, tool_use.input)
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": json.dumps(result)
                        if isinstance(result, (dict, list))
                        else str(result),
                    }
                )

            self.messages.append({"role": "user", "content": tool_results})
