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

## Local publication and startup instructions

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
that MCP rejects. The same conversation can overwrite its title.

The local pane context and Herdr metadata are trusted; this is not authentication
against local processes forging environment variables or tokens. Title wording
is an agent policy: the helper validates form, and cannot detect semantic secrets
in an otherwise valid public title.

`title-instructions.md` is the single canonical policy for both agents: publish
a public abstract Japanese task title after understanding the first request,
refresh on main-topic changes, omit identifiers/secrets/private paths/quotes,
and never read other conversations. Failure must not block the main task.
Reading the helper/venv and connecting to the caller socket must be permitted;
if necessary request ordinary sandbox escalation for that invocation. Setup does
not disable sandboxing or grant broad permissions.

## Parent deployment after review

No production state or global instructions are changed by tests. From the
reviewed worktree, deploy only these explicit files:

```bash
repo=/home/impactaky/shelffiles
for file in server.py public_titles.py set_title.py setup_instructions.py \
  title-instructions.md README.md tests/test_public_titles.py \
  pyproject.toml uv.lock run.sh .gitignore; do
  install -D -m 644 "config/herdr-mcp/$file" "$repo/config/herdr-mcp/$file"
done
chmod 755 "$repo/config/herdr-mcp/run.sh"
uv sync --locked --project "$repo/config/herdr-mcp"
uv run --locked --project "$repo/config/herdr-mcp" python -m unittest discover \
  -s "$repo/config/herdr-mcp/tests" -v
"$repo/config/herdr-mcp/.venv/bin/python" \
  "$repo/config/herdr-mcp/setup_instructions.py" \
  --codex-home "$repo/config/codex" --claude-config-dir "$repo/config/claude"
```

First inspect the task commit against the parent's saved baseline; do not copy
venvs, caches or runtime config trees. Setup defaults to the canonical shelffiles
source directory. `--source-dir` allows an explicit alternative for testing or
deployment. Without explicit targets, Codex uses `$CODEX_HOME` or `~/.codex`;
Claude uses `$CLAUDE_CONFIG_DIR` or `~/.claude`. The managed policy block goes into
Codex `AGENTS.md` (existing `AGENTS.override.md` takes precedence) and Claude
`CLAUDE.md`. Existing text outside the block is preserved, duplicate blocks are
not added, and later runs refresh the block from the canonical document. Setup
preflights malformed markers in both files before writing. It does not touch
Herdr lifecycle hooks or settings. Re-run setup after editing the canonical policy.

Reload the MCP connection using the existing gateway configuration and start new
Codex/Claude conversations so their native global instructions are loaded.
Already running conversations need the canonical policy supplied explicitly;
installation cannot retroactively inject startup instructions. Parent owns
limited live acceptance: publish a synthetic public title from each agent's own
pane, inspect only `agent_list`, update the title, and verify a fresh conversation
in the same pane starts unset until it publishes. Do not read terminal output.
No worker live verification was performed. If Herdr has not yet reported an ID,
publication fails safely and may be retried after that ID becomes available.

## Isolated verification

```bash
UV_CACHE_DIR=/tmp/herdr-public-uv-cache uv run --locked --project config/herdr-mcp \
  python -m unittest discover -s config/herdr-mcp/tests -v
UV_CACHE_DIR=/tmp/herdr-public-uv-cache uv run --locked --project config/herdr-mcp \
  python -m compileall -q config/herdr-mcp/server.py config/herdr-mcp/public_titles.py \
  config/herdr-mcp/set_title.py config/herdr-mcp/setup_instructions.py \
  config/herdr-mcp/tests/test_public_titles.py
bash -n config/herdr-mcp/run.sh
```

Tests use synthetic API fixtures, subprocess stubs and temporary instruction
files, covering disclosure boundaries, binding lifecycle, caller routing,
validation and setup preservation/idempotence. They never connect to Herdr.
