# Herdr public conversation titles

This separate uv project serves one read-only stdio MCP tool, `agent_list`.
It returns a bare JSON array, for example:

```json
[{"title":"公開タイトルの実装","status":"working"}]
```

Each object contains exactly `title` and `status`. Status is `idle`, `working`,
`blocked`, `done`, or `unknown` (including invalid upstream statuses). Only the
`public_title` token is eligible for a title. Missing, malformed, stale or
unverifiable titles are exactly `タイトル未設定`; there is no fallback. No IDs,
paths, agent names, terminal text or other upstream fields are returned. MCP's
structured output schema requires an object root, so this bare array is encoded
in one JSON text content block instead of being wrapped in an object.

The MCP discards inherited `HERDR_*` variables and fixes its socket to
`/home/impactaky/shelffiles/config/herdr/herdr.sock` and its configuration to
`/home/impactaky/shelffiles/config/herdr/config.toml`. The existing `run.sh` SSH
entry, separate lockfile and venv are retained. CLI errors discard stderr;
malformed JSON/envelopes, responses over 2 MB and requests over 20 seconds
produce fixed public errors. No write tools or conversation history storage exist.

## Topic-change publication

```bash
/home/impactaky/shelffiles/config/herdr-mcp/.venv/bin/python \
  /home/impactaky/shelffiles/config/herdr-mcp/set_title.py '公開タイトルの実装'
```

The helper requires inherited `HERDR_ENV=1`, an alphanumeric public pane ID
(such as `w8W:p1`), and an explicit absolute `HERDR_SOCKET_PATH` without control
characters or surrounding whitespace. It rejects absent/empty/invalid socket
paths before invoking Herdr, queries only that explicit pane, and preserves the
caller's socket/config/session routing.
It rejects mismatching pane IDs, absent conversation identities, and mismatching
`CODEX_THREAD_ID` when present. It never selects the UI-focused pane. A moved pane
whose inherited ID no longer matches is rejected; start with a refreshed caller
context rather than choosing another target.

A title is 1–48 Unicode characters, on one line, with no leading/trailing
whitespace, control/format characters or Unicode line separators. The helper
writes only `public_title` and `public_title_binding` metadata under source
`public-title`, scoped to the session's source. The binding hashes all four
`agent_session` fields (`source`, `agent`, `kind`, `value`). Only nonempty `id`
identities matching the current outer Codex/Claude agent kind qualify; stale
session metadata from a different agent kind is rejected. Path-only references
are unverifiable and remain unset. A later conversation in the same pane cannot use the old binding.
An identity change between the helper's read and write leaves a stale binding
that MCP rejects. The same conversation can overwrite its title. The helper
accepts the CLI's empty stdout acknowledgement after a successful metadata write; reads still
require valid JSON envelopes.

The local pane context and Herdr metadata are trusted; this is not authentication
against local processes forging environment variables or tokens. Title wording
is an agent policy: the helper validates form, and cannot detect semantic secrets
in an otherwise valid public title.

`title-instructions.md` is the single canonical policy for both agents. Initial
publication belongs to the installed UserPromptSubmit hook; agents use the
helper only for main-topic changes. Titles omit identifiers, secrets, private
paths and prompt quotations; other conversations are never read. Failure must
not block the main task.
Reading the helper/venv and connecting to the caller socket must be permitted;
if necessary request ordinary sandbox escalation for that invocation. Setup does
not disable sandboxing or grant broad permissions.

## First-prompt initialization

`first_prompt_title.py codex` and `first_prompt_title.py claude` consume bounded
native UserPromptSubmit JSON on stdin. They require inherited Herdr routing and
an exact match between the payload session ID, explicit agent kind and the
current pane's registered session. They query only that pane, never
`transcript_path` or history. Nonempty `agent_id` payloads and Claude payloads
with `cursor_version` or inherited `CURSOR_VERSION` are skipped before inference
so child/non-native prompts cannot initialize a parent pane. A valid bound title
skips inference, including on resume. New conversations in the same pane can initialize again. A nonblocking
per-pane flock prevents concurrent inference; its private temporary-directory
filename hashes socket and pane, and the file is empty. There is no success
cache: only published bound metadata counts, so failures remain retryable.

Both hooks invoke authenticated `codex exec` with `gpt-6-luna` and low effort;
there is no Claude authentication dependency. The invocation ignores user
configuration and execpolicy rules, runs ephemerally in a fresh temporary cwd with a read-only
sandbox, and disables hooks, shell/tools, MCPs, apps, multi-agent execution,
images, web search, sleep, computer use, skill search and shell snapshots.
Bundled skills and host skill discovery are disabled; project document bytes
are zero and skill instructions are excluded. History persistence, analytics
and environment context are disabled. The generic public-title system policy
is the only content in a temporary `model_instructions_file`; the source prompt
is sent only as JSON data on stdin, never shell text or a stored prompt file.
`CODEX_HOME` is retained for existing authentication; other Codex, Claude and
Herdr context variables (including `CLAUDE_CONFIG_DIR`) are stripped. No
credentials are changed, and no permission, sandbox or hook-trust bypass is used.

The bounded JSONL event stream is parsed; it is never treated as title text.
Only the last `agent_message` from a successfully completed turn is eligible.
Reasoning items are ignored. Failed turns, errors, tool/execution events and
unknown event types reject the result and leave initialization retryable. No
model output or diagnostics are logged or persisted by this hook. Semantic
privacy depends on the model following the system policy; title form and
Japanese text are checked locally, with no raw-prompt fallback.

Limits are 256 KiB input, 32 KiB UTF-8 prompt, 64 KiB JSON events, 1 KiB final
message, 1 second for stdin, 12 seconds for generation and 55 seconds overall
after reading stdin. Oversized prompts are skipped rather than truncated. Generation cleanup kills
the process group and drains pipes, including on timeout. All entrypoint errors
exit zero silently and remain retryable on a later prompt. The hook checks the
session binding and existing title again after generation. The final native
read/write pair is not an atomic compare-and-set; a session switch in that tiny
gap produces a stale binding which public readers reject, as with the manual
helper. No title can become valid for a different session through that race.

## Parent deployment after review

The worker does not write production configuration. Review the task commit,
then copy only its changed source files into the production `config/herdr-mcp`
(not private native config trees, venvs or caches). From that reviewed checkout:

```bash
uv sync --locked --project config/herdr-mcp
uv run --locked --project config/herdr-mcp python -m unittest discover \
  -s config/herdr-mcp/tests -v
config/herdr-mcp/.venv/bin/python config/herdr-mcp/setup_instructions.py \
  --source-dir "$PWD/config/herdr-mcp" \
  --codex-home "$PWD/config/codex" --claude-config-dir "$PWD/config/claude"
```

Setup merges one owned command hook into Codex `hooks.json` and Claude
`settings.json`, passing the explicit agent kind. The Python `-X
herdr_public_title_hook=1` argv marker identifies ownership across source moves;
reruns update only that hook, keeping unrelated hook ordering, commands and
other fields semantically unchanged. The hook timeout is 60 seconds. Both
JSON files and both managed instruction blocks are preflighted before any
write. Invalid config aborts installation. No hook trust, approvals or Herdr
integration scripts are changed. JSON formatting can be normalized on updates.

`--source-dir` selects the deployed helper and interpreter directory. Without
explicit targets Codex uses `$CODEX_HOME` or `~/.codex`, and Claude uses
`$CLAUDE_CONFIG_DIR` or `~/.claude`. Policy blocks go into Codex `AGENTS.md`
(existing `AGENTS.override.md` takes precedence) and Claude `CLAUDE.md`. Text
outside the blocks is preserved. Rerun setup after changing the policy or source
location.

Inspect the resulting native config diff: existing notification and SessionStart
integration commands must remain unchanged, alongside exactly one owned
UserPromptSubmit hook in each config. Start fresh Codex and Claude processes to
load hooks/instructions, and complete native hook trust normally if requested.
Codex may require approval of a new or changed hook command; installation does
not silently trust it. Make sure SessionStart has registered an ID before testing.

Parent live acceptance (independently in each agent's own inherited Herdr pane):

1. Start a fresh conversation and submit a synthetic, non-sensitive task such as
   `公開テスト用の並び替え処理を説明してください`. Verify `agent_list` reports
   a short abstract Japanese title automatically, without a manual helper call.
2. Submit another prompt and resume the conversation: the title must remain.
3. Change the main topic and use `set_title.py` from that conversation to verify
   manual topic updates still work. Submit another prompt: preserve that title.
4. Start a replacement conversation in the same pane: the old bound title must
   be unset until the new prompt initializes a new title. Check both agents.
5. Rerun setup and verify no native config diff. If initialization fails, check
   native hook trust and CLI authentication without logging private prompts;
   another prompt should retry. Do not inspect other conversations or transcripts.

Live hook delivery, native trust, authenticated Codex inference and live Herdr
publication remain parent acceptance gaps; isolated tests exercise none of them.

## Isolated verification

```bash
UV_CACHE_DIR=/tmp/herdr-public-uv-cache uv run --locked --project config/herdr-mcp \
  python -m unittest discover -s config/herdr-mcp/tests -v
UV_CACHE_DIR=/tmp/herdr-public-uv-cache uv run --locked --project config/herdr-mcp \
  python -m compileall -q config/herdr-mcp/server.py config/herdr-mcp/public_titles.py \
  config/herdr-mcp/set_title.py config/herdr-mcp/setup_instructions.py \
  config/herdr-mcp/first_prompt_title.py config/herdr-mcp/tests
bash -n config/herdr-mcp/run.sh
```

Tests use synthetic API fixtures, subprocess stubs and temporary instruction
files, covering disclosure boundaries, binding lifecycle, caller routing,
validation and setup preservation/idempotence. They never connect to Herdr.
