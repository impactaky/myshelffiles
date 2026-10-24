"""Synthetic fixtures only. No Herdr socket connections."""
import json
import os
import subprocess
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import public_titles as titles
import server
import set_title
import setup_instructions as setup

PRIVATE = "PRIVATE_MARKER_/private/path"


def agent(session="conversation-one"):
    return {
        "pane_id": "w1:p2", "agent": "codex", "agent_status": "working",
        "agent_session": {"source": "codex-hook", "agent": "codex", "kind": "id", "value": session},
        "terminal_title": PRIVATE, "title": PRIVATE, "cwd": PRIVATE,
        "name": PRIVATE, "workspace_id": PRIVATE, "transcript": PRIVATE,
        "tokens": {},
    }


def publish_fixture(a, title="公開タイトル"):
    a["tokens"] = {"public_title": title, "public_title_binding": titles.binding(a)}
    return a


class MetadataTests(unittest.TestCase):
    def test_exact_fields_no_fallback_and_status(self):
        a = agent()
        self.assertEqual(titles.public_agent(a), {"title": titles.UNSET, "status": "working"})
        for status in (None, [], {}, PRIVATE, 42):
            a["agent_status"] = status
            self.assertEqual(titles.public_agent(a)["status"], "unknown")
        self.assertNotIn(PRIVATE, json.dumps(titles.public_agent(a)))

    def test_binding_update_and_replacement(self):
        a = publish_fixture(agent())
        self.assertEqual(titles.public_agent(a)["title"], "公開タイトル")
        a["tokens"]["public_title"] = "別の主題"
        self.assertEqual(titles.public_agent(a)["title"], "別の主題")
        a["agent_session"]["value"] = "replacement-in-same-pane"
        self.assertEqual(titles.public_agent(a)["title"], titles.UNSET)
        publish_fixture(a, "新しい会話")
        self.assertEqual(titles.public_agent(a)["title"], "新しい会話")

    def test_outer_agent_replacement_with_lagging_session(self):
        for previous, replacement in (("codex", "claude"), ("claude", "codex")):
            with self.subTest(previous=previous):
                a = agent()
                a["agent"] = previous
                a["agent_session"]["agent"] = previous
                publish_fixture(a)
                self.assertEqual(titles.public_agent(a)["title"], "公開タイトル")
                a["agent"] = replacement
                self.assertIsNone(titles.binding(a))
                self.assertEqual(titles.public_agent(a)["title"], titles.UNSET)
                a["agent_session"]["agent"] = replacement
                a["agent_session"]["value"] = "replacement-conversation"
                self.assertEqual(titles.public_agent(a)["title"], titles.UNSET)
                publish_fixture(a, "新しい会話")
                self.assertEqual(titles.public_agent(a)["title"], "新しい会話")

    def test_malformed_unbound_and_unknown_identity(self):
        for tokens in (None, [], {}, {"public_title": "題"},
                       {"public_title": "題", "public_title_binding": "stale"}):
            a = agent()
            a["tokens"] = tokens
            self.assertEqual(titles.public_agent(a)["title"], titles.UNSET)
        for session in (None, {}, PRIVATE, {"source": "s", "agent": "codex", "kind": "path", "value": PRIVATE}):
            a = publish_fixture(agent())
            a["agent_session"] = session
            self.assertEqual(titles.public_agent(a)["title"], titles.UNSET)
        for value in ("", "a" * 49, "line\nline", "\x1b[31m", "題\u2028名", "題\u200b名", " 題", [], None):
            a = publish_fixture(agent(), value)
            self.assertFalse(titles.valid_title(value))
            self.assertEqual(titles.public_agent(a)["title"], titles.UNSET)


class McpTests(unittest.IsolatedAsyncioTestCase):
    async def test_inventory_and_wire_result(self):
        tools = await server.mcp.list_tools()
        self.assertEqual([t.name for t in tools], ["agent_list"])
        self.assertTrue(tools[0].annotations.readOnlyHint)
        a = publish_fixture(agent())
        with patch.object(server, "run_herdr", AsyncMock(return_value={"type": "agent_list", "agents": [a, agent()]})) as run:
            with patch.dict(os.environ, {"HERDR_SOCKET_PATH": PRIVATE, "HERDR_CONFIG_PATH": PRIVATE, "HERDR_PANE_ID": PRIVATE, "HERDR_SESSION": PRIVATE}):
                content = await server.mcp.call_tool("agent_list", {})
            env = run.call_args.kwargs["env"]
            self.assertEqual(env["HERDR_SOCKET_PATH"], titles.HERDR_SOCKET)
            self.assertEqual(env["HERDR_CONFIG_PATH"], titles.HERDR_CONFIG)
            self.assertEqual(sorted(k for k in env if k.startswith("HERDR_")), ["HERDR_CONFIG_PATH", "HERDR_SOCKET_PATH"])
        payload = json.loads(content[0].text)
        self.assertEqual(payload, [{"title": "公開タイトル", "status": "working"}, {"title": titles.UNSET, "status": "working"}])
        self.assertNotIn(PRIVATE, str(content))

    async def test_invalid_shapes_are_safe(self):
        for result in ({"type": PRIVATE, "agents": []}, {"type": "agent_list", "agents": PRIVATE}, {"type": "agent_list", "agents": [PRIVATE]}):
            with patch.object(server, "run_herdr", AsyncMock(return_value=result)):
                with self.assertRaisesRegex(ValueError, "^Invalid Herdr response$"):
                    await server.agent_list()


class HelperTests(unittest.IsolatedAsyncioTestCase):
    def env(self):
        return {"HERDR_ENV": "1", "HERDR_PANE_ID": "w1:p2", "HERDR_SOCKET_PATH": "/tmp/synthetic-caller.sock", "CODEX_THREAD_ID": "conversation-one"}

    async def test_own_target_and_inherited_routing(self):
        a = agent()
        run = AsyncMock(side_effect=[{"type": "agent_info", "agent": a}, {}])
        env = self.env()
        with patch.object(set_title, "run_herdr", run):
            await set_title.publish("公開タイトル", env)
        self.assertEqual(run.call_args_list[0].args, ("agent", "get", "w1:p2"))
        write = run.call_args_list[1]
        self.assertEqual(write.args[:4], ("pane", "report-metadata", "w1:p2", "--source"))
        self.assertIn("public_title=公開タイトル", write.args)
        self.assertIn("public_title_binding=" + titles.binding(a), write.args)
        for call in run.call_args_list:
            self.assertIs(call.kwargs["env"], env)
            self.assertEqual(call.kwargs["env"]["HERDR_SOCKET_PATH"], "/tmp/synthetic-caller.sock")

    async def test_mixed_case_pane_id(self):
        env = self.env()
        env["HERDR_PANE_ID"] = "w8W:p1aB"
        a = agent()
        a["pane_id"] = env["HERDR_PANE_ID"]
        with patch.object(set_title, "run_herdr", AsyncMock(side_effect=[{"type": "agent_info", "agent": a}, {}])) as run:
            await set_title.publish("公開タイトル", env)
        self.assertEqual(run.call_args_list[0].args, ("agent", "get", "w8W:p1aB"))
        self.assertEqual(run.call_args_list[1].args[:3], ("pane", "report-metadata", "w8W:p1aB"))
        a["pane_id"] = "w8w:p1aB"
        with patch.object(set_title, "run_herdr", AsyncMock(return_value={"type": "agent_info", "agent": a})) as run:
            with self.assertRaises(titles.SafeError):
                await set_title.publish("公開タイトル", env)
            self.assertEqual(run.await_count, 1)

    async def test_missing_or_invalid_socket_never_calls_cli(self):
        for socket in (None, "", "relative.sock", " ", " /tmp/caller.sock", "/tmp/caller.sock ",
                       "/tmp/caller\n.sock", "/tmp/caller\0.sock", "/", "/tmp/"):
            with self.subTest(socket=socket):
                env = self.env()
                if socket is None:
                    del env["HERDR_SOCKET_PATH"]
                else:
                    env["HERDR_SOCKET_PATH"] = socket
                with patch.object(set_title, "run_herdr", AsyncMock()) as run:
                    with self.assertRaisesRegex(titles.SafeError, "^Explicit inherited Herdr socket required$"):
                        await set_title.publish("公開タイトル", env)
                    run.assert_not_called()

    async def test_reject_unidentified_and_unsafe_without_cli(self):
        for env, title in (({}, "題"), ({"HERDR_ENV": "1"}, "題"), ({"HERDR_ENV": "1", "HERDR_PANE_ID": "--current"}, "題"), (self.env(), "bad\nline"), (self.env(), "a" * 49)):
            with patch.object(set_title, "run_herdr", AsyncMock()) as run:
                with self.assertRaises(titles.SafeError):
                    await set_title.publish(title, env)
                run.assert_not_called()

    async def test_wrong_pane_missing_or_mismatched_session_no_write(self):
        cases = []
        a = agent()
        a["pane_id"] = "w9:p9"
        cases.append(a)
        a = agent()
        a["agent_session"] = None
        cases.append(a)
        cases.append(agent("replaced-conversation"))
        a = agent()
        a["agent"] = "claude"
        cases.append(a)
        for a in cases:
            with patch.object(set_title, "run_herdr", AsyncMock(return_value={"type": "agent_info", "agent": a})) as run:
                with self.assertRaises(titles.SafeError):
                    await set_title.publish("題", self.env())
                self.assertEqual(run.await_count, 1)

    async def test_claude_identity(self):
        a = agent()
        a["agent_session"]["agent"] = "claude"
        a["agent"] = "claude"
        env = self.env()
        del env["CODEX_THREAD_ID"]
        with patch.object(set_title, "run_herdr", AsyncMock(side_effect=[{"type": "agent_info", "agent": a}, {}])) as run:
            await set_title.publish("日本語の題", env)
        self.assertEqual(run.await_count, 2)


class TransportTests(unittest.IsolatedAsyncioTestCase):
    async def run_fake(self, code):
        # Use a subprocess fixture, not a real Herdr binary or socket.
        with patch.object(titles, "HERDR_BIN", sys.executable):
            return await titles.run_herdr("-c", code, env=dict(os.environ))

    async def test_transport_failures_never_disclose(self):
        cases = [
            (f'import sys; print({PRIVATE!r}, file=sys.stderr); sys.exit(1)', "Herdr request failed"),
            (f'print({PRIVATE!r})', "Invalid Herdr response"),
            (f'print(\'{{"result": "{PRIVATE}"}}\')', "Invalid Herdr response"),
            (f'print({PRIVATE!r} + "x" * 2000001)', "Herdr response too large"),
            ('print("[" * 10000)', "Invalid Herdr response"),
            ('import os\nwhile True: os.write(1, b"x" * 65536)', "Herdr response too large"),
        ]
        for code, message in cases:
            with self.assertRaises(titles.SafeError) as error:
                await self.run_fake(code)
            self.assertEqual(str(error.exception), message)
            self.assertNotIn(PRIVATE, str(error.exception))
        with patch.object(titles, "TIMEOUT", .02):
            with self.assertRaisesRegex(titles.SafeError, "^Herdr request timed out$"):
                await self.run_fake("import time; time.sleep(10)")
        with patch.object(titles, "HERDR_BIN", "/missing/" + PRIVATE):
            with self.assertRaisesRegex(titles.SafeError, "^Herdr unavailable$"):
                await titles.run_herdr(env={})

    async def test_valid_envelope(self):
        self.assertEqual(await self.run_fake('print(\'{"result": {"type": "agent_list", "agents": []}}\')'), {"type": "agent_list", "agents": []})


class SetupTests(unittest.TestCase):
    def test_preserve_idempotence_shared_policy_and_update(self):
        source = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            codex, claude = Path(tmp) / "codex", Path(tmp) / "claude"
            codex.mkdir()
            claude.mkdir()
            c = codex / "AGENTS.md"
            d = claude / "CLAUDE.md"
            c.write_bytes(b"existing codex\r\n")
            d.write_text("existing claude")
            targets = setup.install(source, codex, claude)
            first = [p.read_bytes() for p in targets]
            setup.install(source, codex, claude)
            self.assertEqual(first, [p.read_bytes() for p in targets])
            self.assertTrue(first[0].startswith(b"existing codex\r\n"))
            self.assertTrue(first[1].startswith(b"existing claude"))
            blocks = [p.read_text().split(setup.BEGIN)[1] for p in targets]
            self.assertEqual(blocks[0], blocks[1])
            self.assertNotIn("@SOURCE_DIR@", blocks[0])
            c.write_text(c.read_text() + "\nkeep suffix\n")
            setup.install(source, codex, claude)
            self.assertTrue(c.read_text().endswith("keep suffix\n"))
            self.assertEqual(c.read_text().count(setup.BEGIN), 1)

    def test_environment_targets_and_policy_refresh(self):
        script = Path(setup.__file__)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source with spaces"
            source.mkdir()
            policy = source / "title-instructions.md"
            policy.write_text("first policy @SOURCE_DIR@")
            env = dict(os.environ, CODEX_HOME=str(root / "codex"), CLAUDE_CONFIG_DIR=str(root / "claude"))
            command = [sys.executable, str(script), "--source-dir", str(source)]
            subprocess.run(command, env=env, check=True, capture_output=True)
            codex = root / "codex" / "AGENTS.md"
            claude = root / "claude" / "CLAUDE.md"
            self.assertEqual(codex.read_text(), claude.read_text())
            codex.write_text("prefix\n" + codex.read_text() + "suffix\n")
            policy.write_text("updated policy @SOURCE_DIR@")
            subprocess.run(command, env=env, check=True, capture_output=True)
            self.assertIn("updated policy " + str(source), codex.read_text())
            self.assertNotIn("first policy", codex.read_text())
            self.assertTrue(codex.read_text().startswith("prefix\n"))
            self.assertTrue(codex.read_text().endswith("suffix\n"))
            self.assertEqual(codex.read_text().count(setup.BEGIN), 1)

    def test_missing_files_override_and_malformed_preflight(self):
        source = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            codex, claude = Path(tmp) / "codex", Path(tmp) / "claude"
            setup.install(source, codex, claude)
            override = codex / "AGENTS.override.md"
            override.write_text("override")
            original = (codex / "AGENTS.md").read_bytes()
            setup.install(source, codex, claude)
            self.assertIn(setup.BEGIN, override.read_text())
            self.assertEqual((codex / "AGENTS.md").read_bytes(), original)
            before = override.read_bytes()
            (claude / "CLAUDE.md").write_text(setup.BEGIN)
            with self.assertRaises(ValueError):
                setup.install(source, codex, claude)
            self.assertEqual(override.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
