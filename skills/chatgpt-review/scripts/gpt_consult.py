#!/usr/bin/env python3
"""
GPT Consult — send code + a question to GPT for expert advice.

Usage:
  python gpt_consult.py --question "Why isn't X working?" --files file1.ts file2.ts
  python gpt_consult.py --question "How should I structure auth?" --files src/ --role architect
  python gpt_consult.py --question "Review this design plan" --files plan.md --role designer
  python gpt_consult.py --question "Is this implementation plan solid?" --files plan.md --role implementer
  python gpt_consult.py --question "Is this pattern correct?" --files app.ts --role reviewer

Roles:
  expert      (default) — diagnose issues, suggest fixes, explain behavior
  architect   — high-level design, patterns, trade-offs, technology choices
  reviewer    — focused code review on specific files (not diffs)
  designer    — evaluate design plans for completeness, feasibility, edge cases
  implementer — evaluate implementation plans for sequencing, dependencies, testing
"""

import argparse
import io
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Pricing per 1M tokens (input, output) — update as OpenAI changes pricing
MODEL_PRICING = {
    "gpt-5.4":      (2.50, 10.00),
    "gpt-4.1":      (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1-nano": (0.10, 0.40),
}

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

SYSTEM_PROMPTS = {
    "expert": (
        "You are a senior software engineer with broad expertise across the full stack. "
        "You diagnose issues precisely, explain root causes clearly, and provide specific, "
        "copy-pasteable fixes. When multiple issues exist, rank them by likelihood. Be direct — no filler."
    ),
    "architect": (
        "You are a software architect. Evaluate designs, suggest patterns, identify trade-offs, "
        "and recommend technology choices. Think about scalability, maintainability, and developer "
        "experience. Give concrete recommendations, not abstract advice. Include code examples "
        "when they clarify a point."
    ),
    "reviewer": (
        "You are a senior code reviewer examining specific files (not diffs). Focus on: "
        "bugs, security vulnerabilities, performance issues, error handling gaps, and design "
        "problems. For each issue, state the file, line/area, severity, and a concrete fix. "
        "If the code is solid, say so briefly. Don't manufacture issues."
    ),
    "designer": (
        "You are a senior software designer reviewing a design plan. Evaluate completeness, "
        "feasibility, edge cases, user experience implications, and potential risks. Identify "
        "gaps in requirements, suggest improvements, and flag anything that could cause problems "
        "during implementation. Consider maintainability, testability, and how the design interacts "
        "with existing systems. Be specific and actionable — vague praise is useless."
    ),
    "implementer": (
        "You are a senior engineer reviewing an implementation plan. Evaluate the proposed approach "
        "for technical feasibility, correct sequencing of steps, dependency management, testing "
        "strategy, and deployment considerations. Identify missing steps, risky assumptions, and "
        "suggest concrete improvements. Flag any steps that should be broken down further or "
        "reordered. Consider rollback scenarios and what could go wrong at each stage."
    ),
}


def format_cost(usage, model: str) -> str:
    """Format token usage and estimated cost."""
    input_tokens = usage.prompt_tokens
    output_tokens = usage.completion_tokens
    total_tokens = usage.total_tokens

    pricing = MODEL_PRICING.get(model)
    if pricing:
        input_cost = (input_tokens / 1_000_000) * pricing[0]
        output_cost = (output_tokens / 1_000_000) * pricing[1]
        total_cost = input_cost + output_cost
        return (
            f"Tokens: {input_tokens:,} in / {output_tokens:,} out / {total_tokens:,} total | "
            f"Cost: ${total_cost:.4f} (${input_cost:.4f} in + ${output_cost:.4f} out)"
        )
    return f"Tokens: {input_tokens:,} in / {output_tokens:,} out / {total_tokens:,} total"


def load_api_key() -> str:
    key = os.environ.get("OPENAI_API_KEY")
    if key:
        return key
    search_paths = [
        Path.cwd() / ".env",
        Path.home() / ".env",
    ]
    for env_path in search_paths:
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("OPENAI_API_KEY=") and not line.startswith("#"):
                    return line.split("=", 1)[1].strip().strip("'\"")
    return ""


def find_project_context() -> str:
    """Auto-detect CLAUDE.md project context from the current project."""
    context_parts = []
    # Search for CLAUDE.md files (project root and subdirectories)
    claude_md_paths = [
        Path.cwd() / "CLAUDE.md",
        Path.cwd() / ".claude" / "CLAUDE.md",
    ]
    for p in claude_md_paths:
        if p.exists():
            content = p.read_text(encoding="utf-8", errors="replace")[:5_000]
            context_parts.append(f"### Project Context ({p.name})\n{content}")
            break  # Use first found

    return "\n\n".join(context_parts)


def find_plan_files() -> list[str]:
    """Auto-detect plan files in common locations."""
    plan_dirs = [
        Path.cwd() / "docs" / "superpowers" / "specs",
        Path.cwd() / ".claude" / "plans",
        Path.cwd() / "docs" / "plans",
        Path.cwd() / "docs" / "specs",
    ]
    plan_files = []
    for d in plan_dirs:
        if d.is_dir():
            for f in sorted(d.glob("*.md"), key=lambda x: x.stat().st_mtime, reverse=True):
                plan_files.append(str(f))
    return plan_files


def read_file_or_dir(path_str: str, max_chars: int = 30_000) -> list[tuple[str, str]]:
    """Read a file or all supported files in a directory. Returns [(name, content)]."""
    p = Path(path_str)
    exts = {'.ts', '.tsx', '.js', '.jsx', '.py', '.json', '.md', '.css', '.html', '.yaml', '.yml', '.toml', '.env',
            '.sql', '.go', '.rs', '.java', '.cs', '.rb', '.php', '.sh', '.bat', '.ps1', '.txt'}

    if p.is_file():
        content = p.read_text(encoding="utf-8", errors="replace")
        if len(content) > max_chars:
            content = content[:max_chars] + "\n\n... [truncated]"
        return [(str(p), content)]

    if p.is_dir():
        results = []
        total = 0
        for f in sorted(p.rglob("*")):
            if f.is_file() and f.suffix in exts and 'node_modules' not in str(f):
                content = f.read_text(encoding="utf-8", errors="replace")
                if total + len(content) > max_chars * 3:
                    results.append((str(f), "... [skipped — context limit]"))
                    continue
                total += len(content)
                results.append((str(f), content))
        return results

    return [(path_str, "(file not found)")]


def get_git_context() -> str:
    """Get brief git context for the question."""
    try:
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, encoding="utf-8"
        ).stdout.strip()
        log = subprocess.run(
            ["git", "log", "--oneline", "-5"],
            capture_output=True, text=True, encoding="utf-8"
        ).stdout.strip()
        return f"Branch: {branch}\nRecent commits:\n{log}"
    except Exception:
        return ""


def save_consult(question: str, answer: str, role: str, model: str) -> Path:
    """Save consult to .reviews/ directory."""
    reviews_dir = Path(".reviews")
    reviews_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = reviews_dir / f"consult_{timestamp}.md"
    header = (
        f"# GPT Consult — {role}\n\n"
        f"**Model**: {model}  \n"
        f"**Date**: {datetime.now().strftime('%Y-%m-%d %H:%M')}  \n"
        f"**Question**: {question}\n\n---\n\n"
    )
    filename.write_text(header + answer, encoding="utf-8")
    return filename


def main():
    parser = argparse.ArgumentParser(description="GPT Consult")
    parser.add_argument("--question", "-q", required=True, help="Question to ask GPT")
    parser.add_argument("--files", "-f", nargs="*", default=[], help="Files or directories to include")
    parser.add_argument("--stdin", action="store_true", help="Read additional context from stdin")
    parser.add_argument("--role", "-r", default="expert",
                        choices=["expert", "architect", "reviewer", "designer", "implementer"],
                        help="GPT role (default: expert)")
    parser.add_argument("--model", default="gpt-5.4", help="OpenAI model (default: gpt-5.4)")
    parser.add_argument("--no-save", action="store_true", help="Don't save to file")
    parser.add_argument("--no-stream", action="store_true", help="Disable streaming output")
    parser.add_argument("--git-context", action="store_true", help="Include git branch/log context")
    parser.add_argument("--auto-context", action="store_true", help="Auto-include CLAUDE.md project context")
    parser.add_argument("--auto-plan", action="store_true",
                        help="Auto-detect and include the most recent plan file")
    args = parser.parse_args()

    from openai import OpenAI

    api_key = load_api_key()
    if not api_key:
        print("Error: OPENAI_API_KEY not found.", file=sys.stderr)
        sys.exit(1)

    # Gather file contents
    file_sections = []
    for f in args.files:
        for name, content in read_file_or_dir(f):
            ext = Path(name).suffix.lstrip('.') or 'txt'
            file_sections.append(f"### {name}\n```{ext}\n{content}\n```")

    # Read from stdin if requested
    if args.stdin and not sys.stdin.isatty():
        stdin_content = sys.stdin.read()
        if stdin_content.strip():
            file_sections.append(f"### (stdin)\n```\n{stdin_content}\n```")

    # Auto-detect plan files
    if args.auto_plan:
        plans = find_plan_files()
        if plans:
            latest = plans[0]
            for name, content in read_file_or_dir(latest):
                ext = Path(name).suffix.lstrip('.') or 'md'
                file_sections.append(f"### {name} (auto-detected plan)\n```{ext}\n{content}\n```")
            print(f"Auto-included plan: {latest}")

    if not file_sections and not args.stdin:
        print("No files found. Use -f to specify files, or --stdin to pipe content.", file=sys.stderr)
        sys.exit(1)

    # Build prompt
    parts = [args.question, ""]

    # Auto-include project context
    if args.auto_context:
        project_ctx = find_project_context()
        if project_ctx:
            parts.append(f"## Project Context\n{project_ctx}\n")

    if args.git_context:
        ctx = get_git_context()
        if ctx:
            parts.append(f"## Git Context\n{ctx}\n")

    if file_sections:
        parts.append(f"## Source Files ({len(file_sections)} files)\n")
        parts.append("\n\n".join(file_sections))

    prompt = "\n".join(parts)

    # Truncate if too long
    if len(prompt) > 120_000:
        prompt = prompt[:120_000] + "\n\n... [context truncated]"

    source_desc = f"{len(file_sections)} files" if file_sections else "stdin"
    print(f"Consulting GPT ({args.role}) with {source_desc}...\n")

    client = OpenAI(api_key=api_key)

    if args.no_stream:
        # Non-streaming mode
        response = client.chat.completions.create(
            model=args.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPTS[args.role]},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_completion_tokens=4096,
        )
        answer = response.choices[0].message.content or ""
        print(answer)
        if response.usage:
            print(f"\n{format_cost(response.usage, args.model)}")
    else:
        # Streaming mode
        stream = client.chat.completions.create(
            model=args.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPTS[args.role]},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_completion_tokens=4096,
            stream=True,
            stream_options={"include_usage": True},
        )
        answer_parts = []
        usage = None
        for chunk in stream:
            if chunk.usage:
                usage = chunk.usage
            if chunk.choices and chunk.choices[0].delta.content:
                text = chunk.choices[0].delta.content
                print(text, end="", flush=True)
                answer_parts.append(text)
        print()  # Final newline
        answer = "".join(answer_parts)
        if usage:
            print(f"\n{format_cost(usage, args.model)}")

    if not args.no_save:
        filepath = save_consult(args.question, answer, args.role, args.model)
        print(f"\n---\nConsult saved to {filepath}")


if __name__ == "__main__":
    main()
