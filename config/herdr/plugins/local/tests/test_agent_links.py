#!/usr/bin/env python3
"""Host-free acceptance checks: python3 config/herdr/plugins/local/tests/test_agent_links.py."""
import curses
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest

# Import the plugin for state tests without leaving generated files in its tree.
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / 'agent-links'
spec = importlib.util.spec_from_file_location('agent_links', PLUGIN / 'agent_links.py')
links = importlib.util.module_from_spec(spec)
spec.loader.exec_module(links)
A, B, BAR, SHELL = 'w1:p1', 'w1:p2', 'w1:p3', 'w1:p4'


class AgentLinks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='links $() ')
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.bin = self.base / 'herdr'
        self.bin.symlink_to(ROOT / 'tests/fake_host.py')
        self.fixture = self.base / 'fixture.json'
        self.log = self.base / 'log'
        self.env = dict(os.environ, HERDR_ENV='1', HERDR_PANE_ID=A,
                        HERDR_SOCKET_PATH='/synthetic/socket', HERDR_BIN_PATH=str(self.bin),
                        TEST_LOG=str(self.log), TEST_FIXTURE=str(self.fixture),
                        XDG_STATE_HOME=str(self.base / 'state'))
        self.env.pop('CODEX_THREAD_ID', None)
        self.env.pop('HERDR_PLUGIN_CONTEXT_JSON', None)
        self.data = dict(agent_links=True, focus=A, panes={}, processes={})
        for pane, kind in ((A, 'codex'), (B, 'claude')):
            self.data['panes'][pane] = dict(pane_id=pane, agent=kind, tab_id='w1:t1', workspace_id='w1',
                agent_session=dict(source='herdr:' + kind, agent=kind, kind='id', value='conversation-' + pane))
        for pane in (BAR, SHELL):
            self.data['panes'][pane] = dict(pane_id=pane, tab_id='w1:t1', workspace_id='w1')
        self.save()
        self.host = links.Host(self.env)
        self.store = links.Store(self.env)

    def save(self):
        self.fixture.write_text(json.dumps(self.data))

    def add(self, url='https://example.org/one', name='One', ok=True):
        self.save()
        result = subprocess.run([str(PLUGIN / 'add-link'), url, name], env=self.env,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode == 0, ok, result.stderr)
        if not ok:
            self.assertEqual(len(result.stderr.splitlines()), 1)
        return result

    def bar(self):
        host = links.Host(dict(self.env, HERDR_PANE_ID=BAR))
        bar = links.Bar(host, self.store, A)
        bar.refresh()
        return bar

    def snapshot(self):
        return {p.name: p.read_bytes() for p in self.store.root.glob('*.json')}

    def test_register_isolated_order_duplicate_and_timestamp(self):
        self.add()
        first = self.bar().links[0]['updated_ns']
        self.add('https://example.org/two', 'Two')
        bar = self.bar()
        self.assertEqual([x['name'] for x in bar.links], ['Two', 'One'])
        self.assertEqual(self.store.read(self.host.identity(B)[0]), [])
        self.add(name='New name')
        bar.refresh()
        self.assertEqual([x['name'] for x in bar.links], ['New name', 'Two'])
        self.assertGreater(bar.links[0]['updated_ns'], first)
        self.env['HERDR_PANE_ID'] = B
        self.add('https://example.org/claude', 'Claude')
        self.assertEqual(len(self.store.read(self.host.identity(A)[0])), 2)
        self.assertEqual(len(self.store.read(self.host.identity(B)[0])), 1)

    def test_empty_focus_switch_and_non_agent_focus(self):
        self.assertIn('まだありません', self.bar().lines())
        self.add()
        self.env['HERDR_PANE_ID'] = B
        self.add('https://example.org/b', 'B')
        bar = self.bar()
        self.assertEqual(bar.links[0]['name'], 'One')
        for pane in (B, BAR, SHELL):
            self.data['focus'] = pane
            self.save()
            bar.refresh()
            self.assertEqual([x['name'] for x in bar.links], ['B'])

    def test_selection_copy_exact_bytes_notice_focus_and_delete_persist(self):
        self.add()
        self.add('https://example.org/日本語?q=a&b=2', 'Two')
        bar = self.bar()
        bar.handle(curses.KEY_DOWN, io.StringIO())
        output = io.StringIO()
        bar.handle('\n', output)
        self.assertEqual(output.getvalue(), '\x1b]52;c;aHR0cHM6Ly9leGFtcGxlLm9yZy9vbmU=\x07')
        self.assertIn('コピーしました', bar.message)
        calls = [json.loads(line)['args'] for line in self.log.read_text().splitlines()]
        self.assertEqual(calls[-1], ['agent', 'focus', A])
        bar.handle(curses.KEY_UP, output)
        bar.handle('d', output)
        self.assertEqual([x['name'] for x in self.bar().links], ['One'])
        self.assertFalse(bar.handle('q', output))

    def test_rejections_leave_all_lists_unchanged(self):
        self.add()
        before = self.snapshot()
        for url in ('ftp://example.org', 'javascript:alert(1)', '', 'https://', 'https://host/\x1b]52;',
                    'https://example.org/with space'):
            self.add(url, ok=False)
            self.assertEqual(self.snapshot(), before)
        for setting, value in (('HERDR_ENV', ''), ('HERDR_PANE_ID', B),
                               ('HERDR_SOCKET_PATH', ''), ('CODEX_THREAD_ID', 'wrong')):
            original = self.env.get(setting)
            if setting == 'HERDR_PANE_ID':
                # Simulate a server response that disagrees with the inherited ID.
                self.data['panes'][B]['pane_id'] = A
            self.env[setting] = value
            self.add(ok=False)
            self.assertEqual(self.snapshot(), before)
            if original is None:
                self.env.pop(setting)
            else:
                self.env[setting] = original
        original = self.data['panes'][A]['agent_session']
        for session in (None, dict(original, agent='claude'), dict(original, kind='path'), dict(original, source='')):
            self.data['panes'][A]['agent_session'] = session
            self.add(ok=False)
            self.assertEqual(self.snapshot(), before)
        self.data['panes'][A]['agent_session'] = original

    def test_session_replacement_resume_and_exit(self):
        self.add()
        bar = self.bar()
        original = self.data['panes'][A]['agent_session']['value']
        self.data['panes'][A]['agent_session']['value'] = 'replacement'
        self.save()
        bar.refresh()
        self.assertEqual(bar.links, [])
        # Same conversation again: resume sees the same URLs.
        self.data['panes'][A]['agent_session']['value'] = original
        self.save()
        self.assertEqual(len(self.bar().links), 1)
        self.add(name='Resumed')
        self.data['focus'] = BAR
        self.save()
        bar.refresh()
        self.assertEqual(bar.links[0]['name'], 'Resumed')
        # Herdr clears the pane's agent identity when the agent exits.
        self.data['panes'][A] = dict(pane_id=A, tab_id='w1:t1', workspace_id='w1')
        self.save()
        bar.refresh()
        self.assertEqual(bar.links, [])
        before = self.snapshot()
        self.add(ok=False)
        self.assertEqual(self.snapshot(), before)

    def test_resume_in_other_pane_and_socket_sees_same_links(self):
        self.add()
        session = dict(self.data['panes'][A]['agent_session'])
        self.data['panes'][SHELL] = dict(pane_id=SHELL, agent='codex', tab_id='w1:t1',
                                         workspace_id='w1', agent_session=session)
        self.data['focus'] = SHELL
        self.save()
        host = links.Host(dict(self.env, HERDR_PANE_ID=BAR, HERDR_SOCKET_PATH='/other/socket'))
        bar = links.Bar(host, self.store, SHELL)
        bar.refresh()
        self.assertEqual([item['name'] for item in bar.links], ['One'])

    def test_simultaneous_writers_and_optional_name(self):
        url = 'https://example.org/' + 'a' * 300
        commands = [[str(PLUGIN / 'add-link'), url],
                    [str(PLUGIN / 'add-link'), 'https://example.org/concurrent', 'Concurrent']]
        workers = [subprocess.Popen(command, env=self.env, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE) for command in commands]
        for worker in workers:
            _, error = worker.communicate(timeout=5)
            self.assertEqual(worker.returncode, 0, error)
        items = self.bar().links
        self.assertEqual({x['url'] for x in items}, {url, 'https://example.org/concurrent'})
        self.assertEqual(next(x['name'] for x in items if x['url'] == url), url[:256])
        self.assertFalse(list(self.store.root.glob('*.tmp')))

    def test_toggle_right_split_then_close_only_bar(self):
        manifest = tomllib.loads((PLUGIN / 'herdr-plugin.toml').read_text())
        self.assertEqual(manifest['actions'][0]['contexts'], ['pane'])
        # Invocation context wins over inherited stale pane identity.
        self.env['HERDR_PLUGIN_CONTEXT_JSON'] = json.dumps(dict(focused_pane_id=A))
        self.env['HERDR_PANE_ID'] = 'w9:p9'
        host = links.Host(self.env)
        links.toggle(host)
        calls = [json.loads(line)['args'] for line in self.log.read_text().splitlines()]
        self.assertEqual(calls[-1], ['plugin', 'pane', 'open', '--plugin', 'agent-links', '--entrypoint', 'bar',
            '--placement', 'split', '--target-pane', A, '--direction', 'right', '--focus',
            '--env', 'HERDR_AGENT_LINKS_TARGET=' + A])
        self.data['processes'][BAR] = [dict(pid=1234,
            argv=[sys.executable, str(PLUGIN / 'agent_links.py'), 'bar'])]
        self.save()
        links.toggle(host)
        calls = [json.loads(line)['args'] for line in self.log.read_text().splitlines()]
        self.assertEqual(calls[-1], ['plugin', 'pane', 'close', BAR])


if __name__ == '__main__':
    unittest.main(verbosity=2)
