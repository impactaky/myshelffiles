#!/usr/bin/env python3
"""Attach the same canonical policy to native global instructions, on explicit install."""
from __future__ import annotations

import argparse
import os
from pathlib import Path

BEGIN = "<!-- herdr-public-title:begin -->"
END = "<!-- herdr-public-title:end -->"
DEFAULT_SOURCE = Path("/home/impactaky/shelffiles/config/herdr-mcp")


def managed_text(existing: str, policy: str) -> str:
    block = f"{BEGIN}\n{policy.rstrip()}\n{END}"
    if BEGIN not in existing and END not in existing:
        separator = "" if not existing or existing.endswith("\n\n") else ("\n" if existing.endswith("\n") else "\n\n")
        return existing + separator + block + "\n"
    if existing.count(BEGIN) != 1 or existing.count(END) != 1 or existing.index(BEGIN) > existing.index(END):
        raise ValueError("Malformed managed instruction block; repair markers before setup")
    start = existing.index(BEGIN)
    end = existing.index(END) + len(END)
    return existing[:start] + block + existing[end:]


def install(source: Path, codex_home: Path, claude_dir: Path) -> list[Path]:
    source = source.expanduser().resolve()
    # Embedded text works for both agents without relying on agent-specific imports.
    if any(c in str(source) for c in '\n\r"`$'):
        raise ValueError("Unsupported source path")
    policy = (source / "title-instructions.md").read_text().replace("@SOURCE_DIR@", str(source))
    codex_home = codex_home.expanduser()
    override = codex_home / "AGENTS.override.md"
    targets = [override if override.exists() else codex_home / "AGENTS.md", claude_dir.expanduser() / "CLAUDE.md"]
    if targets[0].resolve() == targets[1].resolve():
        raise ValueError("Instruction targets must differ")
    updates = []
    for target in targets:
        try:
            with target.open(newline="") as stream:
                existing = stream.read()
        except FileNotFoundError:
            existing = ""
        updates.append((target, existing, managed_text(existing, policy)))
    for target, existing, updated in updates:
        if updated != existing:
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("w", newline="") as stream:
                stream.write(updated)
    return targets


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--codex-home", type=Path, default=Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")))
    parser.add_argument("--claude-config-dir", type=Path, default=Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude")))
    args = parser.parse_args()
    for target in install(args.source_dir, args.codex_home, args.claude_config_dir):
        print(target)


if __name__ == "__main__":
    main()
