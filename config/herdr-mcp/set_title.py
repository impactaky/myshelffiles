#!/usr/bin/env python3
"""Publish metadata only for the inherited, identified caller pane."""
from __future__ import annotations

import asyncio
import os
import re
import sys

from public_titles import SafeError, binding, run_herdr, valid_title


async def publish(title: str, env: dict[str, str]) -> None:
    if not valid_title(title):
        raise SafeError("Invalid public title (use 1–48 characters on one line)")
    pane = env.get("HERDR_PANE_ID", "")
    if env.get("HERDR_ENV") != "1" or not re.fullmatch(r"w[0-9]+:p[0-9]+", pane):
        raise SafeError("Identified Herdr caller required")
    # Explicit inherited target: never fall back to the UI-focused pane.
    result = await run_herdr("agent", "get", pane, env=env)
    agent = result.get("agent")
    if result.get("type") != "agent_info" or not isinstance(agent, dict) or agent.get("pane_id") != pane:
        raise SafeError("Identified Herdr caller required")
    identity = binding(agent)
    if identity is None:
        raise SafeError("Conversation identity unavailable")
    session = agent["agent_session"]
    # Codex supplies an independent caller conversation ID when available.
    thread = env.get("CODEX_THREAD_ID")
    if thread and (session["agent"] != "codex" or session["value"] != thread):
        raise SafeError("Conversation identity mismatch")
    await run_herdr(
        "pane", "report-metadata", pane, "--source", "public-title",
        "--applies-to-source", session["source"],
        "--token", f"public_title={title}",
        "--token", f"public_title_binding={identity}", env=env,
    )


def main() -> int:
    try:
        if len(sys.argv) != 2:
            raise SafeError("Usage: set_title.py PUBLIC_TITLE")
        asyncio.run(publish(sys.argv[1], dict(os.environ)))
    except SafeError as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
