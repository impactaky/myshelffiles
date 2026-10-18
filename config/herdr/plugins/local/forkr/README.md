# Local forkr

Derived from [t4t5/herdr-forkr](https://github.com/t4t5/herdr-forkr), pinned
commit `1c1f6130589bf65456b6cdf398abfb5ddc1becad`. The upstream MIT license and
copyright are retained in LICENSE. Runtime dependencies: Bash, jq, Herdr 0.9.3,
and the selected native agent CLI. Nothing here installs integrations or agents.

Local changes add caller guards, explicit model/effort/provider settings, strict
native session validation, config-directory forwarding, and Codex `--no-daemon`.
Startup failures now preserve the child and report its ID on stderr. Success
requires a live child read showing the correct pane, workspace, cwd, agent and
input readiness. A reported child session must differ from the source (and be a
UUID for Codex/Claude). No prompt is sent. No launch retry, approval, session
search, source-pane edit, notification, or cleanup is performed.

The four manual actions and standalone tab/split/workspace modes remain. Bash
replaces POSIX sh so argv and environment arguments stay in arrays. Manual
invocations without a target use the action's focused pane, or `pane current`;
stale HERDR_PANE_ID/HERDR_WORKSPACE_ID variables do not choose the source.

```
bash /absolute/path/to/forkr.sh \
  [--tab | --split [right|down] | --workspace] [--no-focus] \
  [--model MODEL] [--effort EFFORT] [--provider PROVIDER] \
  [--expected-session UUID] [--expected-kind KIND] \
  [--expected-workspace ID] [--expected-cwd PATH] [pane-id | agent-name]
```

Default: a focused new tab. Guards compare against the source's authoritative
`agent get` result before any layout creation. The foreground cwd takes
precedence over cwd. Source cwd must exist and be absolute. With `--no-focus`,
layout creation uses Herdr's no-focus option and no later focus command runs.
Workspace mode intentionally creates a new workspace and validates that ID.

Codex uses `--no-daemon [settings] fork UUID`; Claude uses
`[settings] --resume UUID --fork-session`. Codex efforts are `none`, `minimal`,
`low`, `medium`, `high`, `xhigh`; Claude efforts are `low`, `medium`, `high`,
`max`. Provider is Codex only and must be an existing configured provider name
containing only letters, digits, underscores or hyphens; this plugin does not
create or check provider configuration. Model is one literal argv value (no
control characters or initial hyphen). Pi and OpenCode native forks remain;
effort/provider are rejected for those agents. Omitted settings retain defaults.

Only CODEX_HOME and CLAUDE_CONFIG_DIR are explicitly copied into new panes.
CODEX_THREAD_ID is cleared in the new shell; no caller session identity or
arbitrary environment list is forwarded. Native permission defaults remain.
Shell readiness is bounded to 50 polls at 0.2 seconds, followed by one Herdr
agent-start readiness wait of 60 seconds. Blocked/unknown/working states fail.
The pane is retained for diagnosis on failure. A missing child session report is
allowed if the remaining readiness checks pass; the parent can wait for its ID.

Success stdout is exactly the child pane ID and a newline. Errors go to stderr
with nonzero status. HERDR_BIN_PATH can select the Herdr executable (as upstream).

Run host-free checks from the repository root:

```
python3 config/herdr/plugins/local/tests/test_plugins.py
```
