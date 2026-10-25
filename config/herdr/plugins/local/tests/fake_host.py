#!/usr/bin/env python3
"""Host-free Herdr/agent fixture executable; never delegates to real tools."""
import json
import os
import sys
from pathlib import Path

args = sys.argv[1:]
name = Path(sys.argv[0]).name
with open(os.environ['TEST_LOG'], 'a') as log:
    log.write(json.dumps({'exe': name, 'args': args, 'cwd': os.getcwd(),
                          'thread': os.environ.get('CODEX_THREAD_ID'),
                          'socket': os.environ.get('HERDR_SOCKET_PATH'),
                          'session': os.environ.get('HERDR_SESSION'),
                          'codex_home': os.environ.get('CODEX_HOME'),
                          'claude_config': os.environ.get('CLAUDE_CONFIG_DIR')}) + '\n')
if name != 'herdr':
    sys.exit(0)
fixture = json.loads(Path(os.environ['TEST_FIXTURE']).read_text())
if fixture.get('agent_links'):
    panes = fixture['panes']
    if args[:2] == ['pane', 'current']:
        result = {'pane': {'pane_id': fixture['focus']}}
    elif args[:2] == ['agent', 'get']:
        result = {'type': 'agent_info', 'agent': panes.get(args[2], {})}
    elif args[:2] == ['pane', 'get']:
        result = {'pane': panes[args[2]]}
    elif args[:2] == ['pane', 'list']:
        result = {'panes': list(panes.values())}
    elif args[:2] == ['pane', 'process-info']:
        pane = args[args.index('--pane') + 1]
        result = {'process_info': {'pane_id': pane,
                  'foreground_processes': fixture.get('processes', {}).get(pane, [])}}
    elif args[:2] == ['agent', 'focus'] or args[:3] in (
            ['plugin', 'pane', 'open'], ['plugin', 'pane', 'close']):
        result = {'type': 'ok'}
    else:
        sys.exit('unexpected Herdr operation: ' + repr(args))
    print(json.dumps({'result': result}))
    sys.exit(0)
source = fixture['source']
child = dict(source, pane_id='child', interactive_ready=True,
             launch_pending=False, agent_status='idle',
             agent_session=dict(source.get('agent_session') or {},
                                value='22222222-2222-4222-8222-222222222222'))
child.update(fixture.get('child', {}))
if args[:2] == ['pane', 'current']:
    result = {'pane': {'pane_id': 'focused-other'}}
elif args[:2] == ['agent', 'get']:
    if args[2] == 'child':
        result = {'agent': child}
    elif args[2] in ('source', 'named-source'):
        result = {'agent': source}
    else:
        sys.exit('unexpected focused pane queried')
elif args[:2] in (['tab', 'create'], ['pane', 'split'], ['workspace', 'create']):
    result = ({'pane': {'pane_id': 'child'}} if args[:2] == ['pane', 'split']
              else {'root_pane': {'pane_id': 'child'}})
    if args[:2] == ['workspace', 'create']:
        result['workspace'] = {'workspace_id': 'new-workspace'}
elif args[:2] == ['pane', 'process-info']:
    result = {'process_info': {'shell_pid': 10, 'foreground_processes':
                               [{'pid': 11 if fixture.get('shell_timeout') else 10}]}}
elif args[:2] == ['agent', 'start']:
    if fixture.get('start_error'):
        print(json.dumps({'error': {'code': fixture['start_error']}}))
        sys.exit(1)
    result = {'type': 'agent_started', 'agent': child, 'argv': args}
elif args[:2] == ['agent', 'rename']:
    result = {'type': 'ok'}
else:
    sys.exit('unexpected Herdr operation: ' + repr(args))
print(json.dumps({'result': result}))
