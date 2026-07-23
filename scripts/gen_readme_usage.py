#!/usr/bin/env python3
"""gen_readme_usage.py -- Regenerate README.md Usage section from live --help output.

Usage:
    python scripts/gen_readme_usage.py           # update README.md in-place
    python scripts/gen_readme_usage.py --check   # exit 1 if README is stale

Wire into CI as a check step:
    python scripts/gen_readme_usage.py --check
"""

from __future__ import annotations
import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
README = ROOT / "README.md"

BEGIN_MARKER = "<!-- BEGIN AUTO-GENERATED USAGE -->"
END_MARKER   = "<!-- END AUTO-GENERATED USAGE -->"

SUBCOMMANDS = [
    [],
    ["inspect"],
    ["explain"],
    ["kill"],
    ["kill-process"],
    ["list"],
    ["docker"],
    ["conflicts"],
    ["watch"],
    ["interactive"],
    ["mcp"],
]


def run_help(sub):
    cmd = [sys.executable, "-m", "kport"] + sub + ["--help"]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT / "src"))
    return (result.stdout or result.stderr).strip()


def build_usage_block():
    lines = [BEGIN_MARKER, ""]
    for sub in SUBCOMMANDS:
        heading = ("kport " + " ".join(sub)) if sub else "kport"
        lines.append("### `" + heading + " --help`")
        lines.append("")
        lines.append("```")
        lines.append(run_help(sub))
        lines.append("```")
        lines.append("")
    lines.append(END_MARKER)
    return "\n".join(lines)


def update_readme(new_block, check_only=False):
    text = README.read_text(encoding="utf-8")
    if BEGIN_MARKER not in text or END_MARKER not in text:
        print("WARNING: Markers not found in README. Appending usage block at end.")
        updated = text.rstrip() + "\n\n" + new_block + "\n"
    else:
        before = text[: text.index(BEGIN_MARKER)]
        after  = text[text.index(END_MARKER) + len(END_MARKER):]
        updated = before + new_block + after
    if updated == text:
        return False
    if check_only:
        return True
    README.write_text(updated, encoding="utf-8")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Regenerate README usage section from --help output"
    )
    parser.add_argument(
        "--check", action="store_true",
        help="Exit 1 if README is stale instead of updating it",
    )
    args = parser.parse_args()
    block   = build_usage_block()
    changed = update_readme(block, check_only=args.check)
    if args.check:
        if changed:
            print("README.md Usage section is STALE. Run: python scripts/gen_readme_usage.py")
            return 1
        print("README.md Usage section is up to date.")
        return 0
    print("README.md updated." if changed else "README.md already up to date.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
