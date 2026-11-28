#!/usr/bin/env bash
set -Eeuo pipefail
[[ $# -eq 0 ]] || { printf 'usage: run.sh\n' >&2; exit 2; }
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
export UV_CACHE_DIR="$script_dir/.cache/uv"
# SSH stdio clients may start without the interactive shell's PATH.
SHELFFILES="$(cd -- "$script_dir/../.." && pwd -P)"
. "$SHELFFILES/entrypoint/env.sh" >&2
if ! command -v herdr >/dev/null; then
    export PATH="$XDG_DATA_HOME/mise/shims:$PATH"
fi
exec uv run --quiet --locked --project "$script_dir" python "$script_dir/server.py"
