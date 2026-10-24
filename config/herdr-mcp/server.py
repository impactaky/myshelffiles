#!/usr/bin/env python3
"""Read-only public titles for the fixed default Herdr session."""
from __future__ import annotations

import json
import os

from mcp.server.fastmcp import FastMCP
from mcp.types import TextContent, ToolAnnotations

from public_titles import HERDR_CONFIG, HERDR_SOCKET, SafeError, public_agent, run_herdr

mcp = FastMCP(
    "herdr-default", log_level="WARNING",
    instructions=("Read-only public conversation titles and lifecycle status in the default "
                  "Herdr session. agent_list returns a bare JSON list with only title and status. "
                  "Missing or unverifiable titles are タイトル未設定. No conversation history is exposed."),
)


@mcp.tool(annotations=ToolAnnotations(
    readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False,
), structured_output=False)
async def agent_list() -> list[TextContent]:
    """Return a JSON array of {title: string, status: idle|working|blocked|done|unknown}."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("HERDR_")}
    env.update(HERDR_SOCKET_PATH=HERDR_SOCKET, HERDR_CONFIG_PATH=HERDR_CONFIG)
    try:
        result = await run_herdr("agent", "list", env=env)
        agents = result.get("agents")
        if result.get("type") != "agent_list" or not isinstance(agents, list) or not all(isinstance(a, dict) for a in agents):
            raise SafeError("Invalid Herdr response")
        public = [public_agent(a) for a in agents]
    except SafeError as error:
        # Never forward upstream stderr, payload, IDs or paths.
        raise ValueError(str(error)) from None
    # MCP outputSchema requires an object root; text JSON preserves the required bare list.
    return [TextContent(type="text", text=json.dumps(public, ensure_ascii=False))]


if __name__ == "__main__":
    mcp.run(transport="stdio")
