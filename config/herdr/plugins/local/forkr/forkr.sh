#!/usr/bin/env bash
# Derived from t4t5/herdr-forkr 1c1f6130589bf65456b6cdf398abfb5ddc1becad.
# MIT; see LICENSE. Fork without changing the source pane.
set -euo pipefail
herdr=${HERDR_BIN_PATH:-herdr}
fail() { printf 'forkr: %s\n' "$*" >&2; exit 1; }
dest=tab direction=right focus=--focus target=''
model='' effort='' provider='' expected_session='' expected_kind='' expected_workspace='' expected_cwd=''
while (($#)); do
  case $1 in
    --tab) dest=tab;;
    --workspace) dest=workspace;;
    --split) dest='split'; case ${2:-} in right|down) direction=$2; shift;; esac;;
    --no-focus) focus=--no-focus;;
    --model|--effort|--provider|--expected-session|--expected-kind|--expected-workspace|--expected-cwd)
      [[ $# -ge 2 && -n ${2:-} ]] || fail "missing value for $1"
      case $1 in
        --model) model=$2;; --effort) effort=$2;; --provider) provider=$2;;
        --expected-session) expected_session=$2;; --expected-kind) expected_kind=$2;;
        --expected-workspace) expected_workspace=$2;; --expected-cwd) expected_cwd=$2;;
      esac
      shift;;
    -h|--help)
      printf '%s\n' 'Usage: forkr.sh [--tab | --split [right|down] | --workspace] [--no-focus]' \
        '  [--model MODEL] [--effort EFFORT] [--provider PROVIDER]' \
        '  [--expected-session UUID] [--expected-kind KIND]' \
        '  [--expected-workspace ID] [--expected-cwd PATH] [pane-id | agent-name]'
      exit 0;;
    -*) fail "unknown option $1";;
    *) [[ -z $target ]] || fail 'only one source target is allowed'; target=$1;;
  esac
  shift
done
command -v jq >/dev/null || fail 'jq is required'
# Manual actions use invocation focus, never a stale workspace/cwd environment.
if [[ -z $target && -n ${HERDR_PLUGIN_CONTEXT_JSON:-} ]]; then
  target=$(jq -er '.focused_pane_id // empty' <<< "$HERDR_PLUGIN_CONTEXT_JSON") || fail 'no focused pane in context'
fi
if [[ -z $target ]]; then
  target=$("$herdr" pane current | jq -er '.result.pane.pane_id') || fail 'no focused pane'
fi
info=$("$herdr" agent get "$target") || fail "cannot inspect source $target"
field() { jq -er ".result.agent.$1 // empty" <<< "$info"; }
kind=$(field agent) || fail 'missing agent kind'
pane_id=$(field pane_id) || fail 'missing source pane'
workspace=$(field workspace_id) || fail 'missing workspace'
cwd=$(field foreground_cwd || field cwd) || fail 'missing cwd'
[[ $cwd == /* && -d $cwd ]] || fail 'source cwd must be an existing absolute directory'
ref=$(field agent_session.value) || fail 'missing native session reference'
ref_kind=$(field agent_session.kind) || fail 'missing native reference kind'
ref_agent=$(field agent_session.agent) || fail 'missing session agent'
[[ $kind == "$ref_agent" ]] || fail 'agent/session-agent mismatch'
[[ -z $expected_session || $ref == "$expected_session" ]] || fail 'session guard mismatch'
[[ -z $expected_kind || $kind == "$expected_kind" ]] || fail 'kind guard mismatch'
[[ -z $expected_workspace || $workspace == "$expected_workspace" ]] || fail 'workspace guard mismatch'
[[ -z $expected_cwd || $cwd == "$expected_cwd" ]] || fail 'cwd guard mismatch'
uuid='^[[:xdigit:]]{8}-[[:xdigit:]]{4}-[[:xdigit:]]{4}-[[:xdigit:]]{4}-[[:xdigit:]]{12}$'
case $kind in
  codex|claude) [[ $ref_kind == id && $ref =~ $uuid ]] || fail 'invalid native UUID reference';;
  pi) [[ ( $ref_kind == id || $ref_kind == path ) && $ref != -* && ! $ref =~ [[:cntrl:]] ]] || fail 'invalid Pi reference';;
  opencode) [[ $ref_kind == id && $ref != -* && ! $ref =~ [[:cntrl:]] ]] || fail 'invalid OpenCode reference';;
  *) fail "no fork recipe for $kind";;
esac
[[ -z $model || ( $model != -* && ! $model =~ [[:cntrl:]] ) ]] || fail 'invalid model'
args=()
case $kind in
  codex)
    args=(--no-daemon)
    case $effort in ''|none|minimal|low|medium|high|xhigh) ;; *) fail 'invalid Codex effort';; esac
    [[ -z $provider || $provider =~ ^[a-zA-Z0-9_-]+$ ]] || fail 'invalid provider'
    [[ -z $effort ]] || args+=(-c "model_reasoning_effort=\"$effort\"")
    [[ -z $provider ]] || args+=(-c "model_provider=\"$provider\"")
    [[ -z $model ]] || args+=(--model "$model")
    args+=(fork "$ref");;
  claude)
    [[ -z $provider ]] || fail 'provider is Codex only'
    case $effort in ''|low|medium|high|max) ;; *) fail 'invalid Claude effort';; esac
    [[ -z $effort ]] || args+=(--effort "$effort")
    [[ -z $model ]] || args+=(--model "$model")
    args+=(--resume "$ref" --fork-session);;
  pi|opencode)
    [[ -z $effort && -z $provider ]] || fail 'effort/provider unsupported for this agent'
    [[ -z $model ]] || args+=(--model "$model")
    if [[ $kind == pi ]]; then args+=(--fork "$ref"); else args+=(--session "$ref" --fork); fi;;
esac
# Forward only known configuration locations. Explicitly clear stale identity in
# the new shell as well as this worker; do not copy the caller's environment.
env_args=(--env CODEX_THREAD_ID=)
[[ ! ${CODEX_HOME+x} ]] || env_args+=(--env "CODEX_HOME=$CODEX_HOME")
[[ ! ${CLAUDE_CONFIG_DIR+x} ]] || env_args+=(--env "CLAUDE_CONFIG_DIR=$CLAUDE_CONFIG_DIR")
unset CODEX_THREAD_ID
case $dest in
  tab) out=$("$herdr" tab create --workspace "$workspace" --cwd "$cwd" "$focus" "${env_args[@]}") || fail 'could not create tab';;
  split) out=$("$herdr" pane split "$pane_id" --direction "$direction" --cwd "$cwd" "$focus" "${env_args[@]}") || fail 'could not split pane';;
  workspace) out=$("$herdr" workspace create --cwd "$cwd" "$focus" "${env_args[@]}") || fail 'could not create workspace';;
esac
new_pane=$(jq -er '.result.pane.pane_id // .result.root_pane.pane_id' <<< "$out") || fail "no child pane in response: $out"
child_fail() { fail "child $new_pane: $* (pane preserved)"; }
child_workspace=$workspace
if [[ $dest == workspace ]]; then
  child_workspace=$(jq -er '.result.workspace.workspace_id' <<< "$out") || child_fail 'missing new workspace ID'
fi
ready=no
for ((i=0; i<50; i++)); do
  ready=$("$herdr" pane process-info --pane "$new_pane" | jq -r '
    .result.process_info | if (.foreground_processes | length) == 1
    and (.foreground_processes[0].pid == .shell_pid)
    then "yes" else "no" end') || ready=no
  [[ $ready != yes ]] || break
  sleep 0.2
done
[[ $ready == yes ]] || child_fail 'shell readiness timed out'
started=$("$herdr" agent start "forkr-$$" --kind "$kind" --pane "$new_pane" --timeout 60000 -- "${args[@]}" 2>&1) || child_fail "startup failed: $started"
# Re-read authoritative child state even after agent start reports success.
child=$("$herdr" agent get "$new_pane") || child_fail 'cannot inspect started agent'
jq -e --arg pane "$new_pane" --arg kind "$kind" --arg workspace "$child_workspace" --arg cwd "$cwd" '
  .result.agent | .pane_id == $pane and .agent == $kind
  and .workspace_id == $workspace and (.foreground_cwd // .cwd) == $cwd
  and .interactive_ready == true and (.launch_pending != true)
  and (.agent_status == "idle" or .agent_status == "done")' <<< "$child" >/dev/null || child_fail 'agent is not input-ready or child context differs'
child_ref=$(jq -r '.result.agent.agent_session.value // empty' <<< "$child") || child_fail 'invalid child session report'
if [[ -n $child_ref ]]; then
  jq -e --arg kind "$kind" '.result.agent.agent_session.agent == $kind' <<< "$child" >/dev/null || child_fail 'session-agent mismatch'
  [[ $child_ref != "$ref" ]] || child_fail 'child still reports source session'
  if [[ $kind == codex || $kind == claude ]]; then
    [[ $child_ref =~ $uuid && $(jq -r '.result.agent.agent_session.kind' <<< "$child") == id ]] || child_fail 'invalid child session UUID'
  fi
fi
"$herdr" agent rename "$new_pane" --clear >/dev/null 2>&1 || true
printf '%s\n' "$new_pane"
