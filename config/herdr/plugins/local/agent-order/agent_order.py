#!/usr/bin/env python3
"""Order the Agents sidebar, and focus the agent at the top of that order.

No argument: install the sort order through agent.view.set. It replaces
ui.agent_panel_sort until the server exits or this plugin is disabled.
`top`: focus the first agent in that order. agent.list ignores the view,
so the same SORT is applied here.
"""
import json
import os
import socket
import sys

# Evaluated in order. "status" sorts by name, which happens to give the wanted
# blocked, done, idle, working order; the rare "unknown" lands before "working".
SORT = [
    {"field": "status", "order": "asc"},
    {"field": "workspace_order", "order": "asc"},
    {"field": "state_change_seq", "order": "desc"},
]


def call(method: str, params: dict) -> dict:
    with socket.socket(socket.AF_UNIX) as sock:
        sock.settimeout(10)
        sock.connect(os.environ["HERDR_SOCKET_PATH"])
        request = {"id": "agent-order", "method": method, "params": params}
        sock.sendall(json.dumps(request).encode() + b"\n")
        response = json.loads(sock.makefile().readline())
    if "error" in response:
        raise SystemExit(json.dumps(response["error"]))
    return response["result"]


def focus_top() -> None:
    spaces = call("workspace.list", {})["workspaces"]
    space_order = {space["workspace_id"]: space["number"] for space in spaces}
    fields = {
        "status": lambda agent: agent["agent_status"],
        "workspace_order": lambda agent: space_order[agent["workspace_id"]],
        "state_change_seq": lambda agent: agent["state_change_seq"],
    }
    agents = call("agent.list", {})["agents"]
    # Stable sorts applied from the last key to the first give the SORT order.
    for rule in reversed(SORT):
        agents.sort(key=fields[rule["field"]], reverse=rule["order"] == "desc")
    if agents:
        call("agent.focus", {"target": agents[0]["pane_id"]})


def main() -> int:
    if sys.argv[1:] == ["top"]:
        focus_top()
    else:
        call("agent.view.set",
             {"source": "plugin:agent-order", "label": "order", "sort": SORT})
    return 0


if __name__ == "__main__":
    sys.exit(main())
