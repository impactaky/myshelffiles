#!/usr/bin/env python3
"""Install the shared title policy and owned native prompt hooks explicitly."""
from __future__ import annotations

import argparse
import json
import os
import shlex
from pathlib import Path

BEGIN = "<!-- herdr-public-title:begin -->"
END = "<!-- herdr-public-title:end -->"
DEFAULT_SOURCE = Path(__file__).resolve().parent


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


# This marker is an argv option to the interpreter, not a native config extension.
# It survives source directory changes and uniquely identifies our owned hook.
OWNER = "herdr_public_title_hook=1"


def hook_config(existing: str, source: Path, kind: str) -> str:
    config = json.loads(existing)
    if not isinstance(config, dict):
        raise ValueError("Hook config must be an object")
    hooks = config.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError("hooks must be an object")
    groups = hooks.setdefault("UserPromptSubmit", [])
    if not isinstance(groups, list):
        raise ValueError("UserPromptSubmit must be an array")
    owned = []
    for group in groups:
        if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
            raise ValueError("Invalid hook group")
        for hook in group["hooks"]:
            if not isinstance(hook, dict):
                raise ValueError("Invalid hook")
            command = hook.get("command", "")
            try:
                argv = shlex.split(command) if isinstance(command, str) else []
            except ValueError:
                argv = []
            if (len(argv) == 5 and argv[1:3] == ["-X", OWNER]
                    and Path(argv[3]).name == "first_prompt_title.py"
                    and argv[4] in ("codex", "claude")):
                owned.append((group, hook))
    command = shlex.join([str(source / ".venv/bin/python"), "-X", OWNER,
                          str(source / "first_prompt_title.py"), kind])
    canonical = {"type": "command", "command": command, "timeout": 60}
    if owned:
        group, hook = owned[0]
        hook.clear()
        hook.update(canonical)
        for extra_group, extra_hook in owned[1:]:
            extra_group["hooks"].remove(extra_hook)
        groups[:] = [g for g in groups if g["hooks"] or g not in [x[0] for x in owned[1:]]]
    else:
        groups.append({"hooks": [canonical]})
    if existing and config == json.loads(existing):
        return existing
    return json.dumps(config, ensure_ascii=False, indent=2) + "\n"


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
    # Preflight native configs too, before changing any instructions or hooks.
    hook_targets = [(codex_home / "hooks.json", "codex"), (claude_dir.expanduser() / "settings.json", "claude")]
    for target, kind in hook_targets:
        existing = target.read_text() if target.exists() else ""
        updates.append((target, existing, hook_config(existing if target.exists() else "{}", source, kind)))
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
