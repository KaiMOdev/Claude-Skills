---
name: chatgpt-review
description: >
  Send code to OpenAI ChatGPT 5.4 for structured code review, design review, implementation plan
  review, architecture advice, or expert consultation. Use this skill whenever the user asks to:
  review code/commits with GPT, get a second opinion, consult GPT about a problem, ask GPT for
  advice on architecture/design, review a design plan, review an implementation plan, debug with
  GPT, or mentions "gpt review" / "ask gpt" / "consult gpt" / "what does gpt think" /
  "chatgpt review" / "second opinion". Also triggers for: "review my commit", "gpt advice",
  "ask openai", "check with gpt", "gpt debug", "design review", "implementation review",
  "architecture review".
argument-hint: "[review-type or question]"
---

# ChatGPT Second Brain

Use OpenAI ChatGPT 5.4 as a second model for code review, design review, implementation review,
debugging advice, and architecture consultation. Two models catch more than one — different
training means different blind spots.

## Prerequisites

- `OPENAI_API_KEY` in environment or any `.env` file in the project root or home directory
- Python 3.10+ with `openai` package installed (`pip install openai`)

## Python Discovery

Find the Python executable in this order:
1. `PYTHON_PATH` environment variable (if set)
2. `python3` command
3. `python` command

Test with: `python3 --version` or `python --version`

## Six Modes

### 1. Code Review (`gpt_review.py`)

Review git diffs — committed, staged, or ranges. Best for: post-commit quality checks, pre-PR review, catching bugs.

```bash
# Last commit
python ${CLAUDE_SKILL_DIR}/scripts/gpt_review.py

# Specific commit
python ${CLAUDE_SKILL_DIR}/scripts/gpt_review.py abc1234

# Range of commits
python ${CLAUDE_SKILL_DIR}/scripts/gpt_review.py HEAD~3..HEAD

# Staged changes
python ${CLAUDE_SKILL_DIR}/scripts/gpt_review.py --staged

# Different model
python ${CLAUDE_SKILL_DIR}/scripts/gpt_review.py --model gpt-4.1
```

**Output**: Categorized issues (Bugs, Security, Performance, Error Handling, Design) with severity, file:line, explanation, fix suggestion. Ends with Verdict and Risk Level.

### 2. Expert Consult (`gpt_consult.py`)

Send specific files + a question to GPT. Best for: debugging, "why doesn't this work", understanding behavior, getting implementation advice.

```bash
python ${CLAUDE_SKILL_DIR}/scripts/gpt_consult.py -q "Why does the login fail on mobile?" -f src/auth.ts hooks/useAuth.ts

# Include a whole directory
python ${CLAUDE_SKILL_DIR}/scripts/gpt_consult.py -q "What's wrong with my API layer?" -f src/services/

# With git context
python ${CLAUDE_SKILL_DIR}/scripts/gpt_consult.py -q "Why did this break?" -f src/api.ts --git-context
```

### 3. Design Review (`gpt_consult.py --role designer`)

Review design plans and specifications. Best for: evaluating completeness, feasibility, edge cases, UX implications.

```bash
python ${CLAUDE_SKILL_DIR}/scripts/gpt_consult.py -q "Review this design plan for gaps and risks" -f design-plan.md -r designer

# With related source files for context
python ${CLAUDE_SKILL_DIR}/scripts/gpt_consult.py -q "Is this design feasible given our current architecture?" -f design.md src/core/ -r designer
```

### 4. Implementation Review (`gpt_consult.py --role implementer`)

Review implementation plans and strategies. Best for: evaluating sequencing, dependencies, testing strategy, deployment risks.

```bash
python ${CLAUDE_SKILL_DIR}/scripts/gpt_consult.py -q "Review this implementation plan — any missing steps or risks?" -f implementation-plan.md -r implementer

# With codebase context
python ${CLAUDE_SKILL_DIR}/scripts/gpt_consult.py -q "Is this migration plan safe?" -f migration-plan.md src/db/ -r implementer
```

### 5. Architecture Consult (`gpt_consult.py --role architect`)

High-level design advice. Best for: "how should I structure X", pattern selection, technology choices, scalability questions.

```bash
python ${CLAUDE_SKILL_DIR}/scripts/gpt_consult.py -q "Should I use SSE or WebSockets for realtime updates?" -f src/server.ts src/api/ -r architect
```

### 6. File Review (`gpt_consult.py --role reviewer`)

Review specific files (not diffs). Best for: reviewing files that weren't recently changed, auditing specific modules.

```bash
python ${CLAUDE_SKILL_DIR}/scripts/gpt_consult.py -q "Review this for security issues" -f src/auth/middleware.ts -r reviewer
```

## Workflow when invoked as a skill

Determine what the user wants and pick the right mode:

| User says | Mode | Script |
|-----------|------|--------|
| "review my commit", "gpt review", "review changes" | **Code Review** | `gpt_review.py` |
| "review this design", "evaluate the design plan" | **Design Review** | `gpt_consult.py -r designer` |
| "review this implementation plan", "check the plan" | **Impl Review** | `gpt_consult.py -r implementer` |
| "gpt advice on architecture", "how should I design X" | **Architecture** | `gpt_consult.py -r architect` |
| "have gpt review this file", "audit this code" | **File Review** | `gpt_consult.py -r reviewer` |
| "ask gpt about X", "consult gpt", "why doesn't X work" | **Expert** | `gpt_consult.py` |

### For code reviews:
1. Determine what to review (HEAD, staged, range, specific commit)
2. Run the review script via Bash
3. Present results in a table format
4. Offer to fix issues GPT found

### For consults/reviews:
1. Identify the relevant files for the question
2. If reviewing a plan file, pass the plan file as `-f`
3. Run the consult script with the appropriate role via Bash
4. Present GPT's response
5. If GPT suggests changes, offer to implement them

## Options

Both scripts share:
- `--model MODEL` — override model (default: gpt-5.4)
- `--no-save` — don't save output to `.reviews/`
- `--no-stream` — disable streaming (wait for full response)

Review-specific:
- `--staged` — review staged changes
- `--json` — machine-readable output (implies --no-stream)
- `ref` — git ref or range (default: HEAD)

Consult-specific:
- `-q`/`--question` — the question to ask
- `-f`/`--files` — files or directories to include as context
- `-r`/`--role` — expert (default), architect, reviewer, designer, or implementer
- `--stdin` — read additional context from stdin (pipe content directly)
- `--git-context` — include branch and recent commits
- `--auto-context` — auto-include CLAUDE.md project context
- `--auto-plan` — auto-detect and include the most recent plan file

## Streaming & Cost Tracking

Both scripts stream responses by default — output appears token-by-token as GPT generates it.
After each call, token usage and estimated cost are displayed:

```
Tokens: 2,450 in / 890 out / 3,340 total | Cost: $0.0150 ($0.0061 in + $0.0089 out)
```

Use `--no-stream` to wait for the full response before printing.

## Piping Content

You can pipe content directly to `gpt_consult.py` without needing files on disk:

```bash
# Pipe a plan from another command
cat my-plan.md | python ${CLAUDE_SKILL_DIR}/scripts/gpt_consult.py -q "Review this plan" --stdin -r designer

# Pipe clipboard or any other source
echo "Should I use Redis or Memcached for session storage?" | python ${CLAUDE_SKILL_DIR}/scripts/gpt_consult.py -q "Advise on this" --stdin -r architect
```

## Auto-Context

Use `--auto-context` to automatically include CLAUDE.md project context, giving GPT awareness of the project's conventions and structure:

```bash
python ${CLAUDE_SKILL_DIR}/scripts/gpt_consult.py -q "Review this design" -f design.md -r designer --auto-context
```

Use `--auto-plan` to automatically find and include the most recent plan file from `docs/superpowers/specs/`, `.claude/plans/`, or `docs/plans/`:

```bash
python ${CLAUDE_SKILL_DIR}/scripts/gpt_consult.py -q "Is this implementation plan solid?" --auto-plan -r implementer
```

## History

All reviews and consults are saved to `.reviews/` with timestamps:
- `review_YYYYMMDD_HHMMSS.md` — code reviews
- `consult_YYYYMMDD_HHMMSS.md` — consultations

## Tips

- For debugging: include ALL files in the data flow, not just the one that errors
- For design review: include existing architecture docs alongside the new plan
- For implementation review: include related source code so GPT can assess feasibility
- For large diffs: review by commit range instead of all at once (80K char limit)
- Compare GPT's take with Claude's for maximum coverage — different models catch different things
- Use `--git-context` when the question relates to recent changes
- Use `--model gpt-4.1-mini` for cheaper, faster reviews on non-critical code
