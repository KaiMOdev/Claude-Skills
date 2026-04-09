#!/usr/bin/env python3
"""
GPT Code Review — sends a git diff to OpenAI GPT and returns structured feedback.

Usage:
  python gpt_review.py                    # Review last commit
  python gpt_review.py HEAD~3..HEAD       # Review range
  python gpt_review.py --staged           # Review staged changes
  python gpt_review.py abc123             # Review specific commit
  python gpt_review.py --model gpt-4.1    # Override model

Requires: OPENAI_API_KEY environment variable
"""

import argparse
import io
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Fix Windows console encoding for emoji/unicode
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')


def get_diff(ref: str, staged: bool = False) -> tuple[str, str]:
    """Get the git diff and a description of what's being reviewed."""
    if staged:
        cmd = ["git", "diff", "--staged"]
        desc = "staged changes"
    elif ".." in ref:
        cmd = ["git", "diff", ref]
        desc = f"commits {ref}"
    elif ref == "HEAD":
        cmd = ["git", "diff", "HEAD~1..HEAD"]
        desc = "last commit"
    else:
        # Specific commit
        cmd = ["git", "diff", f"{ref}~1..{ref}"]
        desc = f"commit {ref[:8]}"

    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        print(f"Error getting diff: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    return result.stdout, desc


def get_commit_info(ref: str) -> str:
    """Get commit messages for context."""
    if ".." in ref:
        log_ref = ref
    elif ref == "HEAD":
        log_ref = "-1"
    else:
        log_ref = f"-1 {ref}"

    cmd = f"git log --format='%h %s' {log_ref}"
    result = subprocess.run(cmd, capture_output=True, text=True, shell=True, encoding="utf-8", errors="replace")
    return result.stdout.strip()


def get_changed_files(ref: str, staged: bool = False) -> str:
    """Get list of changed files with stats."""
    if staged:
        cmd = ["git", "diff", "--staged", "--stat"]
    elif ".." in ref:
        cmd = ["git", "diff", "--stat", ref]
    elif ref == "HEAD":
        cmd = ["git", "diff", "--stat", "HEAD~1..HEAD"]
    else:
        cmd = ["git", "diff", "--stat", f"{ref}~1..{ref}"]

    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return result.stdout.strip()


REVIEW_PROMPT = """\
You are a senior code reviewer. Review the following git diff and provide structured, actionable feedback.

## Review Guidelines

Focus on issues that actually matter. Skip nitpicks about style or formatting unless they hurt readability.

### Categories to evaluate:

1. **Bugs & Correctness** — Logic errors, off-by-one, null/undefined access, race conditions, wrong assumptions
2. **Security** — Injection, XSS, secrets in code, insecure defaults, missing auth checks, OWASP top 10
3. **Performance** — N+1 queries, unnecessary re-renders, missing memoization, O(n^2) where O(n) is easy
4. **Error Handling** — Swallowed errors, missing try/catch at boundaries, unhelpful error messages
5. **Design** — Coupling, missing abstractions (only if clear), dead code, unused imports

### Output format:

For each issue found, use this format:

**[CATEGORY] severity: high|medium|low**
`file:line` — one-line summary
> Explanation of why this matters and what to do instead.
> Include a code suggestion if the fix isn't obvious.

At the end, provide:

**Summary**: 1-2 sentences on overall quality.
**Verdict**: APPROVE | REQUEST_CHANGES | COMMENT
**Risk level**: LOW | MEDIUM | HIGH — how likely is this diff to cause a production issue?

If the code looks solid, say so briefly. Don't manufacture issues to seem thorough.

---

## Context

Commit(s): {commit_info}

Changed files:
{changed_files}

## Diff

```diff
{diff}
```
"""


def load_api_key() -> str:
    """Load OPENAI_API_KEY from environment or .env files."""
    key = os.environ.get("OPENAI_API_KEY")
    if key:
        return key

    # Search for .env files in common locations
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


def call_gpt(diff: str, commit_info: str, changed_files: str, model: str) -> str:
    """Send the diff to OpenAI and get the review."""
    from openai import OpenAI

    api_key = load_api_key()
    if not api_key:
        print("Error: OPENAI_API_KEY not found.", file=sys.stderr)
        print("Add it to your .env file:  OPENAI_API_KEY=sk-...", file=sys.stderr)
        print("Or set it:  export OPENAI_API_KEY=sk-...", file=sys.stderr)
        sys.exit(1)

    # Truncate very large diffs to stay within context limits
    max_diff_chars = 80_000
    if len(diff) > max_diff_chars:
        diff = diff[:max_diff_chars] + "\n\n... [diff truncated — too large for single review] ..."

    prompt = REVIEW_PROMPT.format(
        diff=diff,
        commit_info=commit_info,
        changed_files=changed_files,
    )

    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are a precise, experienced code reviewer. Be direct and actionable."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
        max_completion_tokens=4096,
    )

    return response.choices[0].message.content


def save_review(review: str, desc: str, model: str) -> Path:
    """Save review to .reviews/ directory."""
    reviews_dir = Path(".reviews")
    reviews_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = reviews_dir / f"review_{timestamp}.md"

    header = f"# Code Review — {desc}\n\n**Model**: {model}  \n**Date**: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n---\n\n"
    filename.write_text(header + review, encoding="utf-8")

    return filename


def main():
    parser = argparse.ArgumentParser(description="GPT Code Review")
    parser.add_argument("ref", nargs="?", default="HEAD", help="Git ref or range (default: HEAD)")
    parser.add_argument("--staged", action="store_true", help="Review staged changes")
    parser.add_argument("--model", default="gpt-5.4", help="OpenAI model (default: gpt-5.4)")
    parser.add_argument("--no-save", action="store_true", help="Don't save review to file")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    # Get the diff
    diff, desc = get_diff(args.ref, args.staged)
    if not diff.strip():
        print("No changes to review.")
        sys.exit(0)

    commit_info = get_commit_info(args.ref) if not args.staged else "(staged changes)"
    changed_files = get_changed_files(args.ref, args.staged)

    print(f"Reviewing {desc} with {args.model}...\n")

    # Call GPT
    review = call_gpt(diff, commit_info, changed_files, args.model)

    if args.json:
        output = {
            "model": args.model,
            "ref": desc,
            "review": review,
            "timestamp": datetime.now().isoformat(),
        }
        print(json.dumps(output, indent=2))
    else:
        print(review)

    # Save to file
    if not args.no_save:
        filepath = save_review(review, desc, args.model)
        print(f"\n---\nReview saved to {filepath}")


if __name__ == "__main__":
    main()
