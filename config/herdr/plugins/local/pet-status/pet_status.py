#!/usr/bin/env python3
"""Report the agent status of every pane and workspace as a pet icon.

Each pane and workspace gets its icon in the token named after its status
(`$pet_idle`, `$pet_working`, ...); the other status tokens are cleared.
[ui.sidebar.agents].rows and [ui.sidebar.spaces].rows list all of those
tokens, each with its own color, so only the current one shows.
Icons are two-cell glyphs in the private use area of the pet icon font.
"""
import fcntl
import json
import os
import subprocess
import sys
import tempfile

PET = os.environ.get("HERDR_PET", "cat")
SOURCE = "pet-status"

# Glyph pairs start at U+E900, in font order.
FRAMES = ["idle", "thinking", "working", "success", "error", "sleep"]
PETS = ["dog", "cat"]

# Herdr agent status -> icon frame.
STATUS_FRAME = {
    "idle": "idle",
    "working": "working",
    "blocked": "error",
    "done": "success",
    "unknown": "sleep",
}


def icon(pet: str, frame: str) -> str:
    base = 0xE900 + 2 * (PETS.index(pet) * len(FRAMES) + FRAMES.index(frame))
    return chr(base) + chr(base + 1)


def herdr(*args: str) -> str:
    binary = os.environ.get("HERDR_BIN_PATH", "herdr")
    return subprocess.run(
        [binary, *args], check=True, capture_output=True, text=True, timeout=10
    ).stdout


def wanted_tokens(status: str) -> dict:
    if status not in STATUS_FRAME:
        status = "unknown"
    return {f"pet_{status}": icon(PET, STATUS_FRAME[status])}


def report(kind: str, target_id: str, want: dict, *extra: str) -> bool:
    args = []
    for status in STATUS_FRAME:
        name = f"pet_{status}"
        args += ["--token", f"{name}={want[name]}"] if name in want else ["--clear-token", name]
    try:
        herdr(kind, "report-metadata", target_id, "--source", SOURCE, *args, *extra)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as err:
        print(f"{target_id}: {err}", file=sys.stderr)
        return False
    return True


def main() -> int:
    # Serialize runs so the last one to report has read the newest state.
    state_dir = os.environ.get("HERDR_PLUGIN_STATE_DIR") or tempfile.gettempdir()
    lock = open(os.path.join(state_dir, "pet-status.lock"), "w")
    fcntl.flock(lock, fcntl.LOCK_EX)

    ok = True
    # Workspace listings carry no tokens to compare against, so always report.
    for space in json.loads(herdr("workspace", "list"))["result"]["workspaces"]:
        want = wanted_tokens(space.get("agent_status"))
        ok &= report("workspace", space["workspace_id"], want)
    for pane in json.loads(herdr("pane", "list"))["result"]["panes"]:
        want = wanted_tokens(pane.get("agent_status"))
        have = {k: v for k, v in pane.get("tokens", {}).items() if k.startswith("pet")}
        if have == want and not pane.get("state_labels"):
            continue
        ok &= report("pane", pane["pane_id"], want,
                     "--clear-token", "pet", "--clear-state-labels")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
