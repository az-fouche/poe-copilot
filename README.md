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

Run locally for free using [Ollama](https://ollama.com).

```bash
# 1. Install from https://ollama.com/download, then:
ollama serve               # start the server (often auto-starts on install)

# 2. Pull a model (see table below), e.g.:
ollama pull qwen3:14b

# 3. Connect poechat:
poechat --setup            # select Ollama as your backend
```

#### Recommended models by GPU

| GPU tier | VRAM | Model | Size | Speed | Notes |
|----------|------|-------|------|-------|-------|
| xx70 (12 GB) | 12 GB | `qwen3:8b` | ~5 GB | ~80 tok/s | Very dumb |
| xx80 (16 GB) | 16 GB | `qwen3:14b` | ~12 GB | ~62 tok/s | Dumb |
| xx90 (24 GB) | 24 GB | `qwen3:32b` | ~20 GB | ~40 tok/s | Didn't test myself |

Quality is for now clearly inferior compared to commercial LLMs — smaller local models struggle with complex multi-step queries.

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
