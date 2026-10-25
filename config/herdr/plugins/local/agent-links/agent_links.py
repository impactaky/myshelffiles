#!/usr/bin/env python3
"""Agent-scoped storage and a small terminal sidebar; no external dependencies."""
import base64
from contextlib import contextmanager
import curses
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unicodedata
from urllib.parse import urlsplit


class LinkError(Exception):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=True).encode()).hexdigest()


def clean(value):
    return isinstance(value, str) and bool(value.strip()) and not any(
        unicodedata.category(c).startswith('C') or c in '\u2028\u2029' for c in value)


def valid_url(url):
    if not clean(url) or any(c.isspace() for c in url) or len(url) > 8192:
        raise LinkError('http(s) URL required')
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname:
            raise ValueError
        parsed.port
    except ValueError:
        raise LinkError('http(s) URL required') from None
    return url


class Host:
    def __init__(self, env):
        self.env = env
        socket = env.get('HERDR_SOCKET_PATH', '')
        if (env.get('HERDR_ENV') != '1' or not clean(socket) or not os.path.isabs(socket)
                or socket.endswith('/') or socket != socket.strip()):
            raise LinkError('Inherited Herdr socket required')
        override = env.get('HERDR_BIN_PATH', '')
        self.binary = shutil.which(override) if override else None
        self.binary = self.binary or shutil.which('herdr')
        if not self.binary:
            raise LinkError('Herdr unavailable')
        self.socket = socket

    def call(self, *args):
        try:
            result = subprocess.run([self.binary, *args], env=self.env, stdin=subprocess.DEVNULL,
                                    capture_output=True, timeout=3, check=True)
            return json.loads(result.stdout)['result']
        except (OSError, subprocess.SubprocessError, ValueError, KeyError):
            raise LinkError('Herdr request failed') from None

    def identity(self, pane):
        if not isinstance(pane, str) or not re.fullmatch(r'w[A-Za-z0-9]+:p[A-Za-z0-9]+', pane):
            raise LinkError('Identified Herdr pane required')
        result = self.call('agent', 'get', pane)
        if result.get('type') != 'agent_info':
            raise LinkError('Agent identity unavailable')
        agent = result.get('agent', {})
        session = agent.get('agent_session')
        if (agent.get('pane_id') != pane or not isinstance(session, dict)
                or agent.get('agent') not in ('codex', 'claude')
                or session.get('agent') != agent['agent'] or session.get('kind') != 'id'
                or not all(clean(session.get(k)) for k in ('source', 'agent', 'kind', 'value'))):
            raise LinkError('Agent identity unavailable')
        # Session IDs survive resume. Add a live process birth identity so a new
        # occupant of the same pane cannot inherit the previous instance's URLs.
        processes = self.call('pane', 'process-info', '--pane', pane).get('process_info', {})
        if processes.get('pane_id') != pane:
            raise LinkError('Agent process unavailable')
        matches = []
        for process in processes.get('foreground_processes', []):
            argv = process.get('argv') or []
            if not argv:
                continue
            executable = Path(argv[0]).name
            native = (executable == agent['agent']
                      or (agent['agent'] == 'claude' and executable == 'claude.exe'))
            wrapper = (executable in ('node', 'nodejs') and len(argv) > 1
                       and Path(argv[1]).name == agent['agent'])
            if native or wrapper:
                pid = process['pid']
                try:
                    # /proc stat comm may contain spaces and parentheses.
                    stat = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
                    if stat[0] == 'Z':
                        continue
                    matches.append((0 if native else 1, pid, stat[19]))
                except (OSError, IndexError):
                    continue
        if not matches:
            raise LinkError('Live agent process unavailable')
        _, pid, born = min(matches)
        boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        key = digest([self.socket, pane, [session[k] for k in ('source', 'agent', 'kind', 'value')],
                      boot, pid, born])
        return key, agent

    def caller(self):
        key, agent = self.identity(self.env.get('HERDR_PANE_ID'))
        thread = self.env.get('CODEX_THREAD_ID')
        if thread and (agent['agent'] != 'codex' or agent['agent_session']['value'] != thread):
            raise LinkError('Caller conversation mismatch')
        return key, agent


class Store:
    def __init__(self, env):
        self.root = Path(env.get('XDG_STATE_HOME') or Path(env['HOME']) / '.local/state') / 'herdr-agent-links'

    @contextmanager
    def locked(self, key):
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        with (self.root / (key + '.lock')).open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            yield

    def read(self, key):
        if not key:
            return []
        try:
            return json.loads((self.root / (key + '.json')).read_text())
        except FileNotFoundError:
            return []

    def write(self, key, links):
        fd, name = tempfile.mkstemp(dir=self.root, prefix=key, suffix='.tmp')
        try:
            with os.fdopen(fd, 'w') as out:
                json.dump(links, out, ensure_ascii=True)
                out.flush()
                os.fsync(out.fileno())
            os.replace(name, self.root / (key + '.json'))
        finally:
            Path(name).unlink(missing_ok=True)

    def add(self, key, url, name):
        with self.locked(key):
            links = [item for item in self.read(key) if item['url'] != url]
            self.write(key, [dict(url=url, name=name, updated_ns=time.time_ns()), *links])

    def delete(self, key, url):
        with self.locked(key):
            self.write(key, [item for item in self.read(key) if item['url'] != url])


class Bar:
    def __init__(self, host, store, pane):
        self.host, self.store, self.pane = host, store, pane
        self.key = None
        self.agent = None
        self.links = []
        self.selected = 0
        self.message = ''

    def refresh(self):
        focused = self.host.call('pane', 'current')['pane']['pane_id']
        target = focused if focused != self.host.env.get('HERDR_PANE_ID') else self.pane
        try:
            key, agent = self.host.identity(target)
        except LinkError:
            # Non-agent focus preserves the previous agent, but never stale data
            # after that agent exits or is replaced while the bar has focus.
            try:
                key, agent = self.host.identity(self.pane)
            except LinkError:
                self.key, self.agent, self.links = None, None, []
                return
        if key != self.key:
            self.selected, self.message = 0, ''
        self.key, self.agent, self.pane = key, agent, agent['pane_id']
        self.links = self.store.read(key)
        self.selected = min(self.selected, max(0, len(self.links) - 1))

    def lines(self):
        title = 'links: ' + (self.agent['agent'] if self.agent else 'agent 不在')
        rows = [title, 'Enter コピー  d 消す  q 閉じる', self.message]
        if not self.links:
            return rows + ['まだありません']
        for index, link in enumerate(self.links):
            rows.extend([('▸ ' if index == self.selected else '  ') + link['name'], '  ' + link['url']])
        return rows

    def handle(self, key, output):
        if key == 'q':
            return False
        if key in ('j', curses.KEY_DOWN):
            self.selected = min(self.selected + 1, max(0, len(self.links) - 1))
        if key in ('k', curses.KEY_UP):
            self.selected = max(0, self.selected - 1)
        if self.links and key in ('d', '\n', '\r', curses.KEY_ENTER):
            # Recheck the binding immediately before any operation.
            expected = self.key
            url = self.links[self.selected]['url']
            self.refresh()
            if self.key != expected or not any(item['url'] == url for item in self.links):
                return True
            if key == 'd':
                self.store.delete(self.key, url)
                self.refresh()
                self.message = '削除しました'
            else:
                output.write('\x1b]52;c;' + base64.b64encode(url.encode()).decode() + '\x07')
                output.flush()
                self.message = 'コピーしました（手元のブラウザへ貼り付け）'
                self.host.call('agent', 'focus', self.pane)
        return True


def toggle(host):
    context = json.loads(host.env.get('HERDR_PLUGIN_CONTEXT_JSON') or '{}')
    pane = context.get('focused_pane_id') or host.call('pane', 'current')['pane']['pane_id']
    info = host.call('pane', 'get', pane)['pane']
    # Recognize only this plugin's exact bar command, not labels or stale files.
    for other in host.call('pane', 'list', '--workspace', info['workspace_id'])['panes']:
        if other['tab_id'] != info['tab_id']:
            continue
        processes = host.call('pane', 'process-info', '--pane', other['pane_id'])['process_info']
        for process in processes.get('foreground_processes', []):
            argv = process.get('argv') or []
            if len(argv) == 3 and Path(argv[1]) == Path(__file__).resolve() and argv[2] == 'bar':
                host.call('plugin', 'pane', 'close', other['pane_id'])
                return
    host.identity(pane)
    host.call('plugin', 'pane', 'open', '--plugin', 'agent-links', '--entrypoint', 'bar',
              '--placement', 'split', '--target-pane', pane, '--direction', 'right', '--focus',
              '--env', 'HERDR_AGENT_LINKS_TARGET=' + pane)


def run_bar(host, store):
    bar = Bar(host, store, host.env.get('HERDR_AGENT_LINKS_TARGET'))

    def draw(screen):
        screen.timeout(1000)
        while True:
            try:
                bar.refresh()
            except LinkError as error:
                bar.links, bar.message = [], str(error)
            screen.erase()
            height, width = screen.getmaxyx()
            rows = bar.lines()
            # Keep selection visible in short terminals; leave the header fixed.
            offset = max(0, 3 + 2 * bar.selected + 2 - height)
            rows = rows[:3] + rows[3 + offset:]
            for row, line in enumerate(rows[:height]):
                try:
                    screen.addnstr(row, 0, line, max(0, width - 1))
                except curses.error:
                    pass
            screen.refresh()
            try:
                key = screen.get_wch()
            except curses.error:
                continue
            try:
                if not bar.handle(key, sys.stdout):
                    return
            except LinkError as error:
                bar.message = str(error)
    curses.wrapper(draw)


def main(args):
    try:
        host = Host(dict(os.environ))
        store = Store(host.env)
        if args and args[0] == 'add' and len(args) in (2, 3):
            url = valid_url(args[1])
            name = args[2] if len(args) == 3 else url[:256]
            if not clean(name) or len(name) > 256:
                raise LinkError('Name must be 1–256 printable characters')
            key, _ = host.caller()
            store.add(key, url, name)
        elif args == ['toggle']:
            toggle(host)
        elif args == ['bar']:
            run_bar(host, store)
        else:
            raise LinkError('Usage: add-link URL [NAME] | run.sh toggle')
    except (LinkError, OSError, ValueError, KeyError) as error:
        print('agent-links: ' + str(error).splitlines()[0], file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
