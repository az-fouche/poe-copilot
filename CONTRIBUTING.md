# Contributing to PoE Chat

Thanks for your interest in contributing! This is a small community project, so we keep things simple.

## Getting started

```bash
# Fork and clone
git clone https://github.com/<your-fork>/poe-copilot.git
cd poe-copilot

# Install dependencies
uv sync

# Run to verify everything works
poechat
```

You'll need an Anthropic API key — the onboarding flow will prompt you on first launch.

## Running tests

```bash
pytest
```

Tests live in `tests/`. No coverage requirement yet — just make sure existing tests still pass.

## Branch & PR workflow

1. Branch off `main` with a descriptive name (e.g. `feat/add-stash-tool`, `fix/ninja-timeout`)
2. Make your changes
3. Run `pytest` to verify
4. Open a PR against `main`

Keep PRs focused — one feature or fix per PR. 

## Code style

No linter enforced yet. Follow existing patterns:

- Type hints where it helps readability
- `snake_case` for functions and variables
- Docstrings on public functions

## Agent prompts

The agent system prompts live in `src/poe_copilot/agents/*.md`:

| File                | Role                                              |
|---------------------|---------------------------------------------------|
| `router.md`         | Classifies questions and routes to the right agent |
| `researcher.md`     | Investigates using tools, writes research reports  |
| `build_agent.md`    | Composes PoE builds from guides and meta data      |
| `planner.md`        | Decomposes complex questions, delegates to agents  |
| `fact_checker.md`   | Verifies accuracy of research                      |
| `answerer.md`       | Formats research into player-facing responses      |
| `timeline.md`       | League timeline and critical PoE lore (shared context) |

Each agent gets its prompt + dynamic player context (league, mode, experience) injected at runtime via `context.py`.

## Adding tools

Tools live in `src/poe_copilot/tools/`:

1. Create your tool module (e.g. `tools/stash.py`) with tool definitions and a handler function
2. Register the tool in `tools/__init__.py` — add it to `TOOL_DEFINITIONS` and `_HANDLERS`
3. Add a description in `agents/registry.json` under the `"tools"` key

Look at `tools/poe_ninja.py` or `tools/web.py` for examples of the pattern.

## Reporting issues

Use [GitHub Issues](https://github.com/<your-org>/poe-copilot/issues). Include:

- What you expected vs what happened
- Steps to reproduce
- Your Python version and OS
