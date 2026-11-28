"""Shared metadata contract and bounded local CLI transport; no history storage."""
from __future__ import annotations

import asyncio
import hashlib
import json
import unicodedata
from pathlib import Path

HERDR_BIN = "herdr"
HERDR_DIR = Path(__file__).resolve().parents[1] / "herdr"
HERDR_SOCKET = str(HERDR_DIR / "herdr.sock")
HERDR_CONFIG = str(HERDR_DIR / "config.toml")
UNSET = "タイトル未設定"
MAX_TITLE = 48
MAX_RESPONSE = 2_000_000
TIMEOUT = 20


class SafeError(Exception):
    """Only fixed, public messages may cross the CLI/MCP boundary."""


def valid_title(value: object) -> bool:
    return (
        isinstance(value, str) and 0 < len(value) <= MAX_TITLE
        and value == value.strip()
        and not any(unicodedata.category(c).startswith("C") or c in "\u2028\u2029" for c in value)
    )


def binding(agent: dict) -> str | None:
    session = agent.get("agent_session")
    if not isinstance(session, dict):
        return None
    # A path alone is not a verifiable conversation ID; never inspect its contents.
    if session.get("kind") != "id" or session.get("agent") not in ("codex", "claude"):
        return None
    # Detection can change before session metadata catches up after pane reuse.
    if agent.get("agent") != session["agent"]:
        return None
    parts = [session.get(k) for k in ("source", "agent", "kind", "value")]
    if not all(isinstance(p, str) and p.strip() and len(p) <= 4096 for p in parts):
        return None
    return hashlib.sha256(json.dumps(parts, ensure_ascii=True).encode()).hexdigest()


def public_agent(agent: dict) -> dict[str, str]:
    tokens = agent.get("tokens")
    title = UNSET
    identity = binding(agent)
    if isinstance(tokens, dict) and identity and tokens.get("public_title_binding") == identity:
        candidate = tokens.get("public_title")
        if valid_title(candidate):
            title = candidate
    status = agent.get("agent_status")
    if not isinstance(status, str) or status not in ("idle", "working", "blocked", "done", "unknown"):
        status = "unknown"
    return {"title": title, "status": status}


async def run_herdr(*args: str, env: dict[str, str], empty_ack: bool = False) -> dict:
    try:
        process = await asyncio.create_subprocess_exec(
            HERDR_BIN, *args, env=env, stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        )
    except OSError:
        raise SafeError("Herdr unavailable") from None

    async def read() -> bytes:
        chunks = []
        size = 0
        while chunk := await process.stdout.read(65536):
            size += len(chunk)
            if size > MAX_RESPONSE:
                raise SafeError("Herdr response too large")
            chunks.append(chunk)
        await process.wait()
        return b"".join(chunks)

    try:
        raw = await asyncio.wait_for(read(), TIMEOUT)
        if process.returncode:
            raise SafeError("Herdr request failed")
        # report-metadata acknowledges success with no stdout in Herdr 0.9.5.
        if empty_ack and not raw:
            return {}
        try:
            data = json.loads(raw)
        except (ValueError, UnicodeError, RecursionError):
            raise SafeError("Invalid Herdr response") from None
        if not isinstance(data, dict) or not isinstance(data.get("result"), dict):
            raise SafeError("Invalid Herdr response")
        return data["result"]
    except TimeoutError:
        raise SafeError("Herdr request timed out") from None
    finally:
        if process.returncode is None:
            process.kill()
        # Drain the killed child's pipe so a full stdout buffer cannot stall cleanup.
        await process.communicate()
