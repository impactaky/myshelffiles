"""All hook, model and native config fixtures are isolated from live services."""
import asyncio
import copy
from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import first_prompt_title as hook
import set_title
import setup_instructions as setup
import public_titles as titles
from test_public_titles import agent, publish_fixture

ENV = {"HERDR_ENV": "1", "HERDR_PANE_ID": "w1:p2", "HERDR_SOCKET_PATH": "/tmp/fixture.sock"}


def payload(session="conversation-one"):
    return {"hook_event_name": "UserPromptSubmit", "session_id": session,
            "prompt": "$(touch /tmp/never-execute) `false` 秘密の顧客向け機能を修正", "transcript_path": "/never/read"}


def generation_events(title="修正作業"):
    return [
        {"type": "thread.started", "thread_id": "synthetic"},
        {"type": "turn.started"},
        {"type": "item.completed", "item": {"type": "agent_message", "text": title}},
        {"type": "turn.completed", "usage": {}},
    ]


def event_bytes(events):
    return ("\n".join(json.dumps(event, ensure_ascii=False) for event in events) + "\n").encode()


class HookTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        p = patch.object(hook.tempfile, "gettempdir", return_value=self.tmp.name)
        p.start()
        self.addCleanup(p.stop)

    async def test_both_kinds_initialize_duplicate_replace(self):
        for kind in ("codex", "claude"):
            a = agent()
            a["agent"] = a["agent_session"]["agent"] = kind
            a["agent_session"]["source"] = kind + "-hook"
            async def transport(*args, **kwargs):
                self.assertEqual(args[2], "w1:p2")
                if args[0] == "agent":
                    return {"type": "agent_info", "agent": copy.deepcopy(a)}
                publish_fixture(a, "機能の修正")
                return {}
            with patch.object(set_title, "run_herdr", side_effect=transport) as run, patch.object(hook, "generate", AsyncMock(return_value="機能の修正")) as gen:
                await hook.initialize(kind, payload(), ENV)
                self.assertEqual(gen.await_count, 1)
                self.assertEqual(run.await_count, 3)
                await hook.initialize(kind, payload(), ENV)
                self.assertEqual(gen.await_count, 1)
                a["agent_session"]["value"] = "replacement"
                await hook.initialize(kind, payload("replacement"), ENV)
                self.assertEqual(gen.await_count, 2)
                self.assertTrue(hook.initialized(a))

    async def test_invalid_routing_and_payload_no_inference(self):
        for kind in ("codex", "claude"):
            mismatch = agent()
            mismatch["agent"] = mismatch["agent_session"]["agent"] = "claude" if kind == "codex" else "codex"
            for a in (mismatch, agent("wrong"), {**agent(), "pane_id": "w9:p9"}, {**agent(), "agent_session": None}):
                with patch.object(set_title, "run_herdr", AsyncMock(return_value={"type": "agent_info", "agent": a})), patch.object(hook, "generate", AsyncMock()) as gen:
                    with self.assertRaises(titles.SafeError):
                        await hook.initialize(kind, payload(), ENV)
                    gen.assert_not_called()
        for env in ({}, {**ENV, "HERDR_ENV": "0"}, {**ENV, "HERDR_SOCKET_PATH": "relative"}, {**ENV, "HERDR_PANE_ID": "--current"}):
            with patch.object(hook, "generate", AsyncMock()) as gen:
                with self.assertRaises(titles.SafeError):
                    await hook.initialize("codex", payload(), env)
                gen.assert_not_called()
        for p in ([], {}, {**payload(), "prompt": ""}, {**payload(), "session_id": ""}, {**payload(), "hook_event_name": "Stop"}, {**payload(), "prompt": "x" * (hook.MAX_PROMPT + 1)}):
            with patch.object(hook, "current_agent", AsyncMock()) as read:
                await hook.initialize("codex", p, ENV)
                read.assert_not_called()
        with patch.object(hook, "current_agent", AsyncMock()) as read:
            await hook.initialize("other", payload(), ENV)
            read.assert_not_called()

    async def test_children_and_cursor_never_initialize_parent(self):
        for kind in ("codex", "claude"):
            cases = [({**payload(), "agent_id": "child-agent"}, ENV)]
            if kind == "claude":
                cases += [({**payload(), "cursor_version": "1.0"}, ENV),
                          (payload(), {**ENV, "CURSOR_VERSION": "1.0"})]
            for source, env in cases:
                with patch.object(hook, "current_agent", AsyncMock()) as read, patch.object(hook, "generate", AsyncMock()) as gen, patch.object(hook, "write_title", AsyncMock()) as write:
                    await hook.initialize(kind, source, env)
                    read.assert_not_called()
                    gen.assert_not_called()
                    write.assert_not_called()

    async def test_invalid_output_failure_retry_and_preserve(self):
        for output in ("", "a" * 49, "題\n題", "題\u200b名", "English title", None):
            with patch.object(hook, "current_agent", AsyncMock(return_value=agent())), patch.object(hook, "generate", AsyncMock(return_value=output)), patch.object(hook, "write_title", AsyncMock()) as write:
                await hook.initialize("codex", payload(), ENV)
                write.assert_not_called()
        with patch.object(hook, "current_agent", AsyncMock(return_value=agent())), patch.object(hook, "generate", AsyncMock(side_effect=[TimeoutError(), "修正作業"])), patch.object(hook, "write_title", AsyncMock()) as write:
            with self.assertRaises(TimeoutError):
                await hook.initialize("codex", payload(), ENV)
            await hook.initialize("codex", payload(), ENV)
            write.assert_awaited_once()
        with patch.object(hook, "current_agent", AsyncMock(return_value=publish_fixture(agent()))), patch.object(hook, "generate", AsyncMock()) as gen:
            await hook.initialize("codex", payload(), ENV)
            gen.assert_not_called()

    async def test_recheck_identity_and_title(self):
        for changed in (agent("changed"), publish_fixture(agent()), {**agent(), "agent_session": {**agent()["agent_session"], "source": "changed"}}):
            with patch.object(hook, "current_agent", AsyncMock(side_effect=[agent(), changed])), patch.object(hook, "generate", AsyncMock(return_value="修正作業")), patch.object(hook, "write_title", AsyncMock()) as write:
                await hook.initialize("codex", payload(), ENV)
                write.assert_not_called()
        # Real identity check, not only binding comparison.
        with patch.object(set_title, "run_herdr", AsyncMock(side_effect=[{"type": "agent_info", "agent": agent()}, {"type": "agent_info", "agent": agent("changed")}])) as run, patch.object(hook, "generate", AsyncMock(return_value="修正作業")):
            with self.assertRaises(titles.SafeError):
                await hook.initialize("codex", payload(), ENV)
            self.assertEqual(run.await_count, 2)

    async def test_concurrency_and_hashed_empty_lock(self):
        started, finish = asyncio.Event(), asyncio.Event()
        async def generate(*args):
            started.set()
            await finish.wait()
            return "修正作業"
        with patch.object(hook, "current_agent", AsyncMock(return_value=agent())), patch.object(hook, "generate", side_effect=generate) as gen, patch.object(hook, "write_title", AsyncMock()) as write:
            task = asyncio.create_task(hook.initialize("codex", payload(), ENV))
            await started.wait()
            with self.assertRaises(BlockingIOError):
                await hook.initialize("codex", payload(), ENV)
            finish.set()
            await task
            self.assertEqual(gen.await_count, 1)
            write.assert_awaited_once()
        files = list(Path(self.tmp.name).glob("*/*"))
        self.assertEqual(len(files), 1)
        self.assertRegex(files[0].name, "^[a-f0-9]{64}$")
        self.assertEqual(files[0].read_bytes(), b"")


class GeneratorTests(unittest.IsolatedAsyncioTestCase):
    async def test_argv_data_and_isolation(self):
        process = AsyncMock()
        process.pid = 123456789
        process.returncode = 0
        process.stdin = unittest.mock.Mock()
        process.stdin.drain = AsyncMock()
        process.stdout.read = AsyncMock(side_effect=[event_bytes(generation_events()), b""])
        env = {**ENV, "CLAUDECODE": "1", "CLAUDE_CODE_SESSION_ID": "private", "CODEX_THREAD_ID": "private", "CODEX_SESSION_ID": "private", "PATH": "/bin", "CODEX_HOME": "/auth-location", "CLAUDE_CONFIG_DIR": "/private-claude"}
        prompt = payload()["prompt"]
        async def launch(*argv, **kwargs):
            instructions = Path(kwargs["cwd"]) / "instructions.md"
            self.assertEqual(instructions.read_text(), hook.SYSTEM)
            self.assertNotIn(prompt, instructions.read_text())
            self.assertEqual(list(Path(kwargs["cwd"]).iterdir()), [instructions])
            return process
        with patch.object(hook.asyncio, "create_subprocess_exec", side_effect=launch) as spawn, patch.object(hook.os, "killpg") as kill:
            self.assertEqual(await hook.generate(prompt, env), "修正作業")
        argv = spawn.call_args.args
        self.assertEqual(argv[:2], ("codex", "exec"))
        for flag in ("--ignore-user-config", "--ignore-rules", "--ephemeral", "--skip-git-repo-check", "--json"):
            self.assertIn(flag, argv)
        disabled = {argv[i + 1] for i, flag in enumerate(argv) if flag == "--disable"}
        self.assertEqual(disabled, {"hooks", "shell_tool", "multi_agent", "apps", "view_image",
                                   "image_generation", "sleep_tool", "computer_use", "skill_search", "shell_snapshot"})
        config = dict(argv[i + 1].split("=", 1) for i, flag in enumerate(argv) if flag == "-c")
        config = {k: json.loads(v) for k, v in config.items()}
        instructions = config.pop("model_instructions_file")
        self.assertEqual(Path(instructions).parent, Path(spawn.call_args.kwargs["cwd"]))
        self.assertEqual(config, {
            "model": "gpt-6-luna", "model_reasoning_effort": "low",
            "project_doc_max_bytes": 0, "skills.include_instructions": False,
            "skills.bundled.enabled": False, "features.skip_host_skill_discovery": True,
            "suppress_unstable_features_warning": True,
            "tools.update_plan.enabled": False, "web_search": "disabled",
            "analytics.enabled": False, "history.persistence": "none",
            "include_environment_context": False, "mcp_servers": {},
        })
        self.assertEqual(argv[argv.index("--sandbox") + 1], "read-only")
        self.assertEqual(argv[-1], "-")
        self.assertNotIn(prompt, argv)
        self.assertEqual(json.loads(process.stdin.write.call_args.args[0]), {"source_prompt": prompt})
        self.assertEqual(spawn.call_args.kwargs["env"], {"PATH": "/bin", "CODEX_HOME": "/auth-location"})
        self.assertFalse(Path(spawn.call_args.kwargs["cwd"]).exists())
        self.assertTrue(spawn.call_args.kwargs["start_new_session"])
        kill.assert_called_once()

    async def test_event_failures_are_retryable_without_publication(self):
        real_spawn = asyncio.create_subprocess_exec
        unsafe = [
            [{"type": "turn.failed", "error": {"message": "private error"}}],
            generation_events()[:-1],
            generation_events() + [{"type": "error", "message": "private error"}],
            [{"type": "turn.completed"}],
            ["not an object"],
            generation_events("x" * (hook.MAX_OUTPUT + 1)),
        ]
        for kind in ("command_execution", "mcp_tool_call", "web_search", "file_change"):
            unsafe.append([{"type": "item.completed", "item": {"type": kind}}, *generation_events()])
        unsafe.append([{"type": "item.started", "item": {"type": "command_execution"}}, *generation_events()])
        for events in unsafe:
            code = "import os; os.write(1," + repr(event_bytes(events)) + ")"
            async def fake_spawn(*args, **kwargs):
                return await real_spawn(sys.executable, "-c", code, **kwargs)
            with tempfile.TemporaryDirectory() as tmp, patch.object(hook.tempfile, "gettempdir", return_value=tmp), patch.object(hook.asyncio, "create_subprocess_exec", side_effect=fake_spawn), patch.object(hook, "current_agent", AsyncMock(return_value=agent())), patch.object(hook, "write_title", AsyncMock()) as write:
                with self.assertRaises(titles.SafeError):
                    await hook.initialize("codex", payload(), ENV)
                write.assert_not_called()
                with patch.object(hook, "generate", AsyncMock(return_value="修正作業")):
                    await hook.initialize("codex", payload(), ENV)
                write.assert_awaited_once()
        # Reasoning/earlier messages are never used as the final title.
        events = generation_events()
        events[2:2] = [{"type": "item.completed", "item": {"type": "reasoning", "text": "private"}},
                       {"type": "item.completed", "item": {"type": "agent_message", "text": "earlier"}}]
        self.assertEqual(hook.final_message(event_bytes(events)), "修正作業")

    async def test_real_timeout_kills_child_tree_and_output_bounds(self):
        real_spawn = asyncio.create_subprocess_exec
        with tempfile.TemporaryDirectory() as tmp:
            pidfile = Path(tmp) / "pid"
            code = ('import os,time\npid=os.fork()\nif pid==0:\n time.sleep(30)\nelse:\n open(' + repr(str(pidfile)) + ',"w").write(str(pid))\n time.sleep(30)\n')
            async def fake_spawn(*args, **kwargs):
                return await real_spawn(sys.executable, "-c", code, **kwargs)
            with patch.object(hook.asyncio, "create_subprocess_exec", side_effect=fake_spawn), patch.object(hook, "GENERATION_TIMEOUT", .3):
                with self.assertRaises(TimeoutError):
                    await hook.generate("修正", dict(os.environ))
            pid = int(pidfile.read_text())
            # A killed orphan can briefly remain a zombie until the host reaps it.
            state = Path(f"/proc/{pid}/stat")
            if state.exists():
                self.assertEqual(state.read_text().split()[2], "Z")
        for code in ('import os\nwhile True: os.write(1, b"x" * 65536)', 'print("x" * 10000)', 'import sys; sys.exit(1)', 'import os; os.write(1,b"\\xff")'):
            async def fake_spawn(*args, **kwargs):
                return await real_spawn(sys.executable, "-c", code, **kwargs)
            with patch.object(hook.asyncio, "create_subprocess_exec", side_effect=fake_spawn):
                with self.assertRaises((titles.SafeError, UnicodeError)):
                    await hook.generate("修正", dict(os.environ))


class EntryTests(unittest.TestCase):
    def test_model_and_transport_errors_exit_silently(self):
        for error in (TimeoutError(), OSError("private diagnostic"), titles.SafeError("private diagnostic")):
            out, err = io.StringIO(), io.StringIO()
            with tempfile.TemporaryDirectory() as tmp, patch.object(hook.tempfile, "gettempdir", return_value=tmp), patch.dict(os.environ, ENV, clear=True), patch.object(sys, "argv", ["hook", "codex"]), patch.object(hook, "read_payload", return_value=payload()), patch.object(hook, "current_agent", AsyncMock(return_value=agent())), patch.object(hook, "generate", AsyncMock(side_effect=error)), redirect_stdout(out), redirect_stderr(err):
                self.assertEqual(hook.main(), 0)
            self.assertEqual((out.getvalue(), err.getvalue()), ("", ""))

    def test_silent_exit_for_malformed_missing_and_oversized(self):
        script = str(Path(hook.__file__))
        for raw, env in ((b"not json", ENV), (b"[]", ENV), (b"x" * (hook.MAX_INPUT + 1), ENV), (b"{}", {})):
            result = subprocess.run([sys.executable, script, "codex"], input=raw, env=env, capture_output=True, timeout=3)
            self.assertEqual((result.returncode, result.stdout, result.stderr), (0, b"", b""))
        child = subprocess.Popen([sys.executable, script, "codex"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=ENV)
        try:
            child.wait(timeout=3)
            self.assertEqual(child.communicate(), (b"", b""))
        finally:
            if child.poll() is None:
                child.kill()
            child.communicate()


class InstallerTests(unittest.TestCase):
    def test_both_shapes_preserve_idempotence_source_update_preflight(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            codex, claude = root / "codex", root / "claude"
            codex.mkdir(); claude.mkdir()
            source = Path(setup.__file__).parent
            fixtures = []
            for kind, path in (("codex", codex / "hooks.json"), ("claude", claude / "settings.json")):
                original = {"other": {"unchanged": True}, "hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "integration", "timeout": 10}]}], "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "notify", **({"async": True} if kind == "claude" else {})}]}]}}
                path.write_text(json.dumps(original))
                fixtures.append((path, original, kind))
            setup.install(source, codex, claude)
            before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
            setup.install(source, codex, claude)
            self.assertEqual(before, {p: p.read_bytes() for p in before})
            for path, original, kind in fixtures:
                updated = json.loads(path.read_text())
                owned = updated["hooks"]["UserPromptSubmit"].pop()
                self.assertEqual(updated, original)
                self.assertTrue(owned["hooks"][0]["command"].endswith(" " + kind))
                moved = json.loads(setup.hook_config(path.read_text(), root / "new source", kind))
                self.assertEqual(len(moved["hooks"]["UserPromptSubmit"]), 2)
                self.assertIn("new source", moved["hooks"]["UserPromptSubmit"][-1]["hooks"][0]["command"])
            for malformed in ("", "{", "[]", '{"hooks": []}', '{"hooks":{"UserPromptSubmit":{}}}'):
                (claude / "settings.json").write_text(malformed)
                before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
                with self.assertRaises(ValueError):
                    setup.install(source, codex, claude)
                self.assertEqual(before, {p: p.read_bytes() for p in before})

    def test_ownership_does_not_capture_unrelated_command(self):
        source = Path(setup.__file__).parent
        unrelated = {"type": "command", "command": "echo '-X herdr_public_title_hook=1'"}
        config = {"hooks": {"UserPromptSubmit": [{"hooks": [unrelated]}]}}
        updated = json.loads(setup.hook_config(json.dumps(config), source, "codex"))
        self.assertEqual(updated["hooks"]["UserPromptSubmit"][0]["hooks"][0], unrelated)
        self.assertEqual(len(updated["hooks"]["UserPromptSubmit"]), 2)

    def test_duplicate_owned_hooks(self):
        source = Path(setup.__file__).parent
        config = json.loads(setup.hook_config("{}", source, "codex"))
        config["hooks"]["UserPromptSubmit"] *= 2
        updated = json.loads(setup.hook_config(json.dumps(config), source, "codex"))
        self.assertEqual(len(updated["hooks"]["UserPromptSubmit"]), 1)
