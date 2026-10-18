# Local fresh-session launcher

Original local implementation from the Herdr 0.9.3 CLI contract, with exactly two
pane entrypoints: `agent-codex` and `agent-claude`. The rejected
`mkdir700/herdr-config` launcher at commit
`e66f57072102f5a45e969f8eef24e5c1bb70f942` has no license declaration; none of its
scripts or manifest is included. No upstream license grant is asserted for this
original code; it follows the enclosing repository's policy.

Dependencies: Bash, Herdr 0.9.3 and the chosen native agent CLI. There is no
picker, service, startup hook, installer or background process. Explicit pane
opening starts the agent; it never sends a prompt or resumes a conversation.
The parent skill waits for input readiness and sends the literal prompt later.

After the parent has reviewed and linked the plugin, the hnew interface is:

```sh
herdr plugin pane open --plugin agent-launcher --entrypoint agent-codex \
  --placement split --workspace "$caller_workspace" --target-pane "$caller_pane" \
  --cwd "$caller_cwd" --no-focus \
  --env "HERDR_AGENT_LAUNCHER_CWD=$caller_cwd" \
  --env "HERDR_AGENT_LAUNCHER_MODEL=$model" \
  --env "HERDR_AGENT_LAUNCHER_EFFORT=$effort" \
  --env "HERDR_AGENT_LAUNCHER_PROVIDER=$provider"
```

For Claude, use `agent-claude` and omit provider. Cwd is required, absolute and
must exist. Optional empty settings retain native defaults. Model is a literal
argv value (no control characters or initial hyphen). Codex efforts: `none`,
`minimal`, `low`, `medium`, `high`, `xhigh`; Claude efforts: `low`, `medium`,
`high`, `max`. Provider is Codex only, an already configured name containing
letters, digits, underscores or hyphens. Unsupported values fail before exec;
provider configuration and model availability are left to the native CLI.

The manifest expands Herdr's HERDR_PLUGIN_ROOT in a fixed, quoted shell command,
so an unrelated launch cwd cannot change script resolution. The script changes
to the exact supplied cwd, unsets CODEX_THREAD_ID and execs `codex --no-daemon`
or `claude`, plus only the validated settings. CODEX_HOME and CLAUDE_CONFIG_DIR
remain available from the pane environment; pass them with `--env` if the caller
uses nondefault locations. No secret environment enumeration, permission
settings, daemon management or arbitrary native argv interface is added.

Standalone interface (the same environment contract):

```
bash /absolute/path/to/agent-launcher/run-agent.sh codex
bash /absolute/path/to/agent-launcher/run-agent.sh claude
```

This launcher does not itself certify readiness: the hnew caller must inspect
the new pane's authoritative agent state and workspace/cwd/kind before sending
input. Herdr owns placement and focus behavior. No live installation or agent
invocation is part of the tests:

```
python3 config/herdr/plugins/local/tests/test_plugins.py
```
