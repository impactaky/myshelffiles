#!/usr/bin/env python3
"""Run: python3 config/herdr/plugins/local/tests/test_plugins.py"""
import json
import os
from pathlib import Path
import subprocess
import shutil
import tempfile
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]
UUID = '11111111-1111-4111-8111-111111111111'
MODEL = 'model "quoted"; $(touch SHOULD_NOT_EXIST) `false` \\ suffix'


class Plugins(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='herdr plugins $() ')
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.cwd = self.base / 'cwd "quotes"; $(false)'
        self.cwd.mkdir()
        self.bin = self.base / 'bin'
        self.bin.mkdir()
        for name in ('herdr', 'codex', 'claude'):
            (self.bin / name).symlink_to(ROOT / 'tests/fake_host.py')
        (self.bin / 'sleep').write_text('#!/bin/sh\nexit 0\n')
        (self.bin / 'sleep').chmod(0o755)
        self.log = self.base / 'log'
        self.fixture = self.base / 'fixture.json'
        self.data = {'source': dict(agent='codex', pane_id='source',
                     workspace_id='caller-workspace', foreground_cwd=str(self.cwd),
                     cwd='/wrong/fallback', agent_session=dict(agent='codex', kind='id', value=UUID))}
        self.env = dict(os.environ, PATH=str(self.bin) + ':' + os.environ['PATH'],
                        HERDR_BIN_PATH=str(self.bin / 'herdr'), TEST_LOG=str(self.log),
                        TEST_FIXTURE=str(self.fixture), HERDR_WORKSPACE_ID='stale-workspace',
                        HERDR_PANE_ID='stale-pane', CODEX_THREAD_ID='stale-thread',
                        CODEX_HOME=str(self.base / 'codex home'),
                        CLAUDE_CONFIG_DIR=str(self.base / 'claude home'))
        self.env.pop('HERDR_PLUGIN_CONTEXT_JSON', None)
        for setting in ('CWD', 'MODEL', 'EFFORT', 'PROVIDER'):
            self.env.pop('HERDR_AGENT_LAUNCHER_' + setting, None)

    def calls(self):
        return [json.loads(s) for s in self.log.read_text().splitlines()] if self.log.exists() else []

    def run_fork(self, *args, ok=True):
        self.fixture.write_text(json.dumps(self.data))
        result = subprocess.run([str(ROOT / 'forkr/forkr.sh'), *args], env=self.env,
                                cwd=self.base, text=True, capture_output=True)
        if ok:
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, 'child\n')
        else:
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, '')
        return result

    def launch(self, kind, ok=True, manifest=False):
        plugin_root = self.base / 'plugin root " ; $(false)'
        if not plugin_root.exists():
            plugin_root.symlink_to(ROOT / 'agent-launcher', target_is_directory=True)
        self.env.update(HERDR_AGENT_LAUNCHER_CWD=str(self.cwd),
                        HERDR_PLUGIN_ROOT=str(plugin_root))
        if manifest:
            panes = tomllib.loads((ROOT / 'agent-launcher/herdr-plugin.toml').read_text())['panes']
            command = next(p['command'] for p in panes if p['id'] == 'agent-' + kind)
        else:
            command = ['bash', str(ROOT / 'agent-launcher/run-agent.sh'), kind]
        result = subprocess.run(command, env=self.env, cwd=self.base,
                                text=True, capture_output=True)
        self.assertEqual(result.returncode == 0, ok, result.stderr)
        return result

    def test_fork_codex_explicit_context_and_literal_args(self):
        self.run_fork('--split', 'down', '--no-focus', '--model', MODEL, '--effort', 'medium',
                      '--provider', 'custom_provider', '--expected-session', UUID,
                      '--expected-kind', 'codex', '--expected-workspace', 'caller-workspace',
                      '--expected-cwd', str(self.cwd), 'named-source')
        calls = self.calls()
        split = next(c['args'] for c in calls if c['args'][:2] == ['pane', 'split'])
        self.assertEqual(split[:3], ['pane', 'split', 'source'])
        self.assertIn('--no-focus', split)
        self.assertEqual(split[split.index('--cwd') + 1], str(self.cwd))
        self.assertIn('CODEX_THREAD_ID=', split)
        self.assertIn('CODEX_HOME=' + self.env['CODEX_HOME'], split)
        self.assertIn('CLAUDE_CONFIG_DIR=' + self.env['CLAUDE_CONFIG_DIR'], split)
        start = next(c for c in calls if c['args'][:2] == ['agent', 'start'])
        native = start['args'][start['args'].index('--') + 1:]
        self.assertEqual(native, ['--no-daemon', '-c', 'model_reasoning_effort="medium"',
                                 '-c', 'model_provider="custom_provider"', '--model', MODEL, 'fork', UUID])
        self.assertIsNone(start['thread'])
        self.assertFalse((self.base / 'SHOULD_NOT_EXIST').exists())
        self.assertFalse(any(c['args'][:2] == ['pane', 'current'] for c in calls))

    def test_stale_binary_override_falls_back_to_path(self):
        for override in ('missing', 'non-executable'):
            with self.subTest(override=override):
                stale = self.base / override
                if override == 'non-executable':
                    stale.write_text('must not execute')
                self.env['HERDR_BIN_PATH'] = str(stale)
                self.env['HERDR_SOCKET_PATH'] = '/synthetic/socket'
                self.env['HERDR_SESSION'] = 'synthetic-session'
                self.log.unlink(missing_ok=True)
                self.run_fork('--split', '--no-focus', '--expected-session', UUID,
                              '--expected-workspace', 'caller-workspace', 'source')
                self.assertEqual(self.calls()[0]['args'], ['agent', 'get', 'source'])
                self.assertTrue(all(c['socket'] == '/synthetic/socket' and
                                    c['session'] == 'synthetic-session' for c in self.calls()))
                self.log.unlink()
                self.run_fork('--expected-session', 'wrong', 'source', ok=False)
                self.assertEqual([c['args'][:2] for c in self.calls()], [['agent', 'get']])

    def test_no_binary_fails_before_any_tool(self):
        self.env['HERDR_BIN_PATH'] = str(self.base / 'deleted-herdr')
        (self.bin / 'herdr').unlink()
        (self.bin / 'bash').symlink_to(shutil.which('bash'))
        (self.bin / 'jq').symlink_to(ROOT / 'tests/fake_host.py')
        self.env['PATH'] = str(self.bin)
        result = self.run_fork('source', ok=False)
        self.assertIn('no executable Herdr found', result.stderr)
        self.assertEqual(self.calls(), [])

    def test_tab_and_manual_focus_context(self):
        self.env['HERDR_PLUGIN_CONTEXT_JSON'] = '{"focused_pane_id":"source"}'
        self.run_fork('--tab', '--no-focus')
        create = next(c['args'] for c in self.calls() if c['args'][:2] == ['tab', 'create'])
        self.assertEqual(create[create.index('--workspace') + 1], 'caller-workspace')
        self.assertIn('--no-focus', create)

    def test_live_current_focus_supersedes_stale_pane_env(self):
        self.run_fork(ok=False)
        self.assertEqual(self.calls()[0]['args'], ['pane', 'current'])
        self.assertEqual(self.calls()[1]['args'], ['agent', 'get', 'focused-other'])

    def test_claude_fork_and_new_workspace(self):
        self.data['source'].update(agent='claude', agent_session=dict(agent='claude', kind='id', value=UUID))
        self.data['child'] = {'workspace_id': 'new-workspace'}
        self.run_fork('--workspace', '--model', MODEL, '--effort', 'high', 'source')
        start = next(c['args'] for c in self.calls() if c['args'][:2] == ['agent', 'start'])
        self.assertEqual(start[start.index('--') + 1:], ['--effort', 'high', '--model', MODEL,
                                                       '--resume', UUID, '--fork-session'])

    def test_guards_before_any_mutation(self):
        for guard in ('session', 'kind', 'workspace', 'cwd'):
            with self.subTest(guard=guard):
                self.log.unlink(missing_ok=True)
                self.run_fork('--expected-' + guard, 'wrong', 'source', ok=False)
                self.assertEqual([c['args'][:2] for c in self.calls()], [['agent', 'get']])

    def test_invalid_refs_and_settings(self):
        for patch in ({'value': ''}, {'value': 'not-a-uuid'}, {'kind': 'path'}, {'agent': 'claude'}):
            with self.subTest(patch=patch):
                original = self.data['source']['agent_session'].copy()
                self.data['source']['agent_session'].update(patch)
                self.log.unlink(missing_ok=True)
                self.run_fork('source', ok=False)
                self.assertEqual(len(self.calls()), 1)
                self.data['source']['agent_session'] = original
        for options in (['--effort', 'imaginary'], ['--provider', 'x";evil'],
                        ['--model', '--bad'], ['--model'], ['--arbitrary-argv'], ['source', 'source']):
            with self.subTest(options=options):
                self.log.unlink(missing_ok=True)
                self.run_fork(*options, 'source', ok=False)
                self.assertFalse(any(c['args'][:2] in (['pane', 'split'], ['tab', 'create']) for c in self.calls()))

    def test_failed_startup_preserves_child(self):
        scenarios = [{'start_error': 'agent_not_ready'}, {'start_error': 'timeout'},
                     {'shell_timeout': True}, {'child': {'agent_status': 'blocked'}},
                     {'child': {'agent_status': 'unknown'}}, {'child': {'agent_status': 'working'}},
                     {'child': {'interactive_ready': False}}, {'child': {'launch_pending': True}},
                     {'child': {'workspace_id': 'wrong'}}, {'child': {'foreground_cwd': '/wrong'}},
                     {'child': {'agent': 'claude'}},
                     {'child': {'agent_session': dict(agent='claude', kind='id', value=UUID)}},
                     {'child': {'agent_session': dict(agent='codex', kind='id', value='bad')}},
                     {'child': {'agent_session': dict(agent='codex', kind='id', value=UUID)}}]
        for scenario in scenarios:
            with self.subTest(scenario=scenario):
                self.data = {'source': self.data['source'], **scenario}
                self.log.unlink(missing_ok=True)
                result = self.run_fork('--no-focus', 'source', ok=False)
                self.assertIn('child', result.stderr)
                calls = self.calls()
                self.assertLessEqual(sum(c['args'][:2] == ['agent', 'start'] for c in calls), 1)
                self.assertFalse(any('close' in c['args'] or 'prompt' in c['args'] for c in calls))

    def test_missing_ref_and_optional_child_report(self):
        original = self.data['source'].pop('agent_session')
        result = self.run_fork('source', ok=False)
        self.assertIn('missing native session reference', result.stderr)
        self.assertEqual(len(self.calls()), 1)
        self.data['source']['agent_session'] = original
        self.data['child'] = {'agent_session': None}
        self.run_fork('source')

    def test_preserved_pi_and_opencode_recipes(self):
        for kind, ref_kind, ref in (
                ('pi', 'path', str(self.cwd / 'session.jsonl')),
                ('opencode', 'id', 'ses_example')):
            with self.subTest(kind=kind):
                self.log.unlink(missing_ok=True)
                self.data['source'].update(agent=kind,
                    agent_session=dict(agent=kind, kind=ref_kind, value=ref))
                self.run_fork('source')
                start = next(c['args'] for c in self.calls() if c['args'][:2] == ['agent', 'start'])
                expected = ['--fork', ref] if kind == 'pi' else ['--session', ref, '--fork']
                self.assertEqual(start[start.index('--') + 1:], expected)

    def test_fresh_manifest_argv_and_exact_cwd(self):
        for kind in ('codex', 'claude'):
            with self.subTest(kind=kind):
                self.log.unlink(missing_ok=True)
                self.env.update(HERDR_AGENT_LAUNCHER_MODEL=MODEL,
                                HERDR_AGENT_LAUNCHER_EFFORT='medium',
                                HERDR_AGENT_LAUNCHER_PROVIDER='custom' if kind == 'codex' else '')
                self.launch(kind, manifest=True)
                call, = self.calls()
                expected = (['--no-daemon', '-c', 'model_reasoning_effort="medium"',
                             '-c', 'model_provider="custom"'] if kind == 'codex' else ['--effort', 'medium'])
                self.assertEqual(call['args'], expected + ['--model', MODEL])
                self.assertEqual(call['exe'], kind)
                self.assertEqual(call['cwd'], str(self.cwd))
                self.assertIsNone(call['thread'])
                self.assertEqual(call['codex_home'], self.env['CODEX_HOME'])
                self.assertEqual(call['claude_config'], self.env['CLAUDE_CONFIG_DIR'])

    def test_fresh_defaults_and_invalid_inputs(self):
        for kind in ('codex', 'claude'):
            self.log.unlink(missing_ok=True)
            self.launch(kind)
            self.assertEqual(self.calls()[0]['args'], ['--no-daemon'] if kind == 'codex' else [])
        for kind, setting, value in [('codex', 'EFFORT', 'wrong'), ('codex', 'PROVIDER', 'a"b'),
                                     ('claude', 'PROVIDER', 'openai'), ('claude', 'EFFORT', 'xhigh'),
                                     ('codex', 'MODEL', '--flag'), ('codex', 'MODEL', 'bad\nvalue')]:
            with self.subTest(setting=setting, value=value):
                self.log.unlink(missing_ok=True)
                key = 'HERDR_AGENT_LAUNCHER_' + setting
                self.env[key] = value
                self.launch(kind, ok=False)
                self.assertEqual(self.calls(), [])
                del self.env[key]
        self.env['HERDR_AGENT_LAUNCHER_CWD'] = '/missing'
        result = subprocess.run(['bash', str(ROOT / 'agent-launcher/run-agent.sh'), 'codex'],
                                env=self.env, capture_output=True)
        self.assertNotEqual(result.returncode, 0)

    def test_server_091_compatibility_manifest_contract(self):
        # Pin the intended server floor independently of the installed CLI.
        # Static contract checks do not certify a live server's capabilities.
        for plugin in ('forkr', 'agent-launcher'):
            with self.subTest(plugin=plugin):
                manifest = tomllib.loads((ROOT / plugin / 'herdr-plugin.toml').read_text())
                self.assertEqual(manifest['min_herdr_version'], '0.9.1')
                entries_key = 'actions' if plugin == 'forkr' else 'panes'
                self.assertEqual(set(manifest), {
                    'id', 'name', 'version', 'min_herdr_version', 'description',
                    'platforms', entries_key})
                entries = manifest[entries_key]
                if plugin == 'forkr':
                    self.assertEqual({e['id'] for e in entries},
                                     {'tab', 'split', 'split-down', 'workspace'})
                    for entry in entries:
                        self.assertEqual(set(entry), {'id', 'title', 'description', 'contexts', 'command'})
                        self.assertEqual(entry['contexts'], ['pane'])
                else:
                    self.assertEqual({e['id'] for e in entries}, {'agent-codex', 'agent-claude'})
                    for entry in entries:
                        self.assertEqual(set(entry), {'id', 'title', 'placement', 'command'})
                        self.assertEqual(entry['placement'], 'split')

    def test_syntax_manifests_and_no_permission_overrides(self):
        manifests = list(ROOT.glob('*/herdr-plugin.toml'))
        self.assertEqual(len(manifests), 2)
        self.assertEqual({tomllib.loads(p.read_text())['id'] for p in manifests}, {'forkr', 'agent-launcher'})
        for path in manifests:
            manifest = tomllib.loads(path.read_text())
            self.assertFalse({'build', 'startup', 'hooks', 'event_hooks'} & manifest.keys())
        for path in ROOT.rglob('*.sh'):
            subprocess.run(['bash', '-n', str(path)], check=True)
            content = path.read_text()
            for forbidden in ('--dangerously', '--auto', 'eval ', 'agent prompt', 'curl ', 'wget '):
                self.assertNotIn(forbidden, content)


if __name__ == '__main__':
    unittest.main(verbosity=2)
