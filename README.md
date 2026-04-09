# ChatGPT Review — Claude Code Plugin

Get a second opinion from ChatGPT 5.4 on your code, design plans, implementation strategies, and architecture decisions. Two models catch more than one.

## What it does

This plugin adds a `chatgpt-review` skill to Claude Code that calls the OpenAI ChatGPT API to provide independent reviews and consultations. Use it alongside Claude for maximum coverage — different models have different blind spots.

### Review Modes

| Mode | Command | Use Case |
|------|---------|----------|
| **Code Review** | `/chatgpt-review` | Review git diffs (commits, staged, ranges) |
| **Design Review** | "have GPT review this design" | Evaluate design plans for gaps and risks |
| **Implementation Review** | "GPT review this impl plan" | Check step sequencing, dependencies, testing |
| **Architecture Consult** | "ask GPT about architecture" | Pattern selection, trade-offs, scalability |
| **File Review** | "have GPT review this file" | Audit specific files for issues |
| **Expert Consult** | "ask GPT about X" | Debugging, root cause analysis, advice |

## Prerequisites

- **OpenAI API key**: Set `OPENAI_API_KEY` as an environment variable or in a `.env` file
- **Python 3.10+** with the `openai` package:
  ```bash
  pip install openai
  ```

## Installation

### From marketplace
```bash
/plugin install chatgpt-review
```

### Manual (from GitHub)
```bash
/plugin marketplace add KaiMOdev/Claude-Skills
```

## Usage

### Code Review
```
"review my last commit with GPT"
"GPT review HEAD~3..HEAD"
"have ChatGPT review my staged changes"
```

### Design Review
```
"have GPT review this design plan" (with a plan file open or specified)
"ask ChatGPT if this design is feasible"
```

### Implementation Review
```
"GPT review this implementation plan"
"ask ChatGPT about the migration strategy"
```

### Architecture
```
"ask GPT — should I use SSE or WebSockets?"
"get GPT's take on this architecture"
```

### Expert Consult
```
"ask GPT why the auth flow is breaking"
"consult ChatGPT about this error"
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | — | Required. Your OpenAI API key |
| `PYTHON_PATH` | auto-detect | Path to Python executable |

### Model Override

All commands support `--model` to use a different OpenAI model:
- `gpt-5.4` (default) — most capable
- `gpt-4.1` — strong, lower cost
- `gpt-4.1-mini` — fast and cheap for non-critical reviews

## Review History

All reviews and consultations are automatically saved to a `.reviews/` directory in your project:
- `review_YYYYMMDD_HHMMSS.md` — code reviews
- `consult_YYYYMMDD_HHMMSS.md` — consultations

Use `--no-save` to suppress saving.

## License

MIT
