# PoE Chat

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A terminal AI companion for Path of Exile — multi-agent, Claude-powered.

Ask a question about PoE, and the agents research it (web search, poe.ninja prices, build guides) then deliver a sourced answer — all from your terminal.

## Quick demo

```
You: What's the best league starter for Mirage?

  Analyzing your question...
  Researching builds...
  Checking poe.ninja meta...

  Based on poe.ninja ladder data and community tier lists...
  (sourced markdown answer)
```

## Install & run

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/<your-org>/poe-copilot.git
cd poe-copilot
uv sync
```

Launch:

```bash
poechat
```

**PoE Chat is free and open-source, but the AI compute is not.** You need your own Anthropic API key to use it. A typical question costs a few cents; complex multi-agent queries (build plans, fact-checked research) can cost ~$0.10–0.30. Support for other providers (OpenAI, Gemini) and smaller/cheaper models is on the roadmap.

On first launch, onboarding will prompt you for:

1. **Anthropic API key** — get one at [console.anthropic.com](https://console.anthropic.com/)
2. **League** — e.g. Mirage, Standard
3. **Game mode** — Softcore Trade, Hardcore, SSF, HC SSF
4. **Experience level** — Newbie through Veteran

Settings are saved to `~/.poechat/settings.usr`. Re-run onboarding anytime with:

```bash
poechat --setup
```

## Commands

| Command    | Description                     |
|------------|---------------------------------|
| `/quit`    | Exit the chat                   |
| `/clear`   | Clear conversation history      |
| `/setup`   | Re-run onboarding               |
| `Ctrl+C`   | Interrupt and salvage partial results |

## Development

```bash
uv sync --extra dev
pre-commit install
```

This installs [pre-commit](https://pre-commit.com/) hooks that run **ruff** linting and formatting on every commit.

To run the hooks manually against all files:

```bash
pre-commit run --all-files
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for how to get started.

## License

[MIT](LICENSE)
