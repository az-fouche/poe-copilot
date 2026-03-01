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

On first launch, onboarding will prompt you for your backend, league, game mode, and experience level. Settings are saved to `~/.poechat/settings.usr`. Re-run onboarding anytime with:

```bash
poechat --setup
```

## Supported backends

### Anthropic (Claude API)

The default backend. Requires an API key from [console.anthropic.com](https://console.anthropic.com/).

A typical question costs a few cents; complex multi-agent queries (build plans, fact-checked research) can cost ~$0.10–0.30.

### Ollama (local)

Run locally for free using [Ollama](https://ollama.com). 16GB VRAM recommended for 14B models.

```bash
# Install from https://ollama.com/download, then:
ollama pull qwen2.5:14b    # download a model (~9 GB)
ollama serve               # start the server (often auto-starts on install)
poechat --setup            # select Ollama as your backend
```

Quality varies — smaller local models may struggle with complex multi-step queries and tool use.

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

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for how to get started.

## License

[MIT](LICENSE)
