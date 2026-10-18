#!/usr/bin/env bash
# Original local launcher: no prompt, resume, or permission overrides.
set -euo pipefail
fail() { printf 'agent-launcher: %s\n' "$*" >&2; exit 64; }
[[ $# == 1 ]] || fail 'expected one agent kind'
kind=$1
cwd=${HERDR_AGENT_LAUNCHER_CWD:-}
model=${HERDR_AGENT_LAUNCHER_MODEL:-}
effort=${HERDR_AGENT_LAUNCHER_EFFORT:-}
provider=${HERDR_AGENT_LAUNCHER_PROVIDER:-}
[[ $cwd == /* && -d $cwd ]] || fail 'cwd must be an existing absolute directory'
[[ -z $model || ( $model != -* && ! $model =~ [[:cntrl:]] ) ]] || fail 'invalid model'
case $kind in
  codex)
    command=(codex --no-daemon)
    case $effort in ''|none|minimal|low|medium|high|xhigh) ;; *) fail 'invalid Codex effort';; esac
    [[ -z $provider || $provider =~ ^[a-zA-Z0-9_-]+$ ]] || fail 'invalid provider'
    [[ -z $effort ]] || command+=(-c "model_reasoning_effort=\"$effort\"")
    [[ -z $provider ]] || command+=(-c "model_provider=\"$provider\"")
    ;;
  claude)
    command=(claude)
    [[ -z $provider ]] || fail 'provider is Codex only'
    case $effort in ''|low|medium|high|max) ;; *) fail 'invalid Claude effort';; esac
    [[ -z $effort ]] || command+=(--effort "$effort")
    ;;
  *) fail 'unsupported agent kind';;
esac
[[ -z $model ]] || command+=(--model "$model")
unset CODEX_THREAD_ID
cd -- "$cwd"
exec "${command[@]}"
