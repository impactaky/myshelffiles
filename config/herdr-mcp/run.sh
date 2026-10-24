#!/usr/bin/env bash
set -Eeuo pipefail
[[ $# -eq 0 ]] || { printf 'usage: run.sh\n' >&2; exit 2; }
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
export UV_CACHE_DIR="$script_dir/.cache/uv"
exec /home/impactaky/shelffiles/result/bin/uv run --quiet --locked --project "$script_dir" python "$script_dir/server.py"
