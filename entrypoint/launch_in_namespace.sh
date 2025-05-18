#!/bin/bash

set -eu

SCRIPT_DIR="$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)"
SHELFFILES="$(CDPATH='' cd -- "$SCRIPT_DIR/.." && pwd)"
export SHELFFILES="$SHELFFILES"

NAMESPACE_DIR="/run/shelffiles-ns"
mkdir -p "$NAMESPACE_DIR"

NAMESPACE_NAME="shelffiles_$(echo "$SHELFFILES" | tr '/:' '_')"
NAMESPACE_PATH="$NAMESPACE_DIR/$NAMESPACE_NAME"

if [ ! -e "$NAMESPACE_PATH" ]; then
  echo "Error: Namespace does not exist at $NAMESPACE_PATH" >&2
  echo "Please run setup_namespace.sh with sudo first" >&2
  exit 1
fi

NAMESPACE_PID=$(cat "$NAMESPACE_PATH")

if ! kill -0 "$NAMESPACE_PID" 2>/dev/null; then
  echo "Error: Namespace process is not running" >&2
  echo "Please run setup_namespace.sh with sudo again" >&2
  rm -f "$NAMESPACE_PATH"
  exit 1
fi

exec nsenter --target "$NAMESPACE_PID" --mount --pid -- "$@"
