#!/bin/bash

set -eu

SCRIPT_DIR="$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)"
SHELFFILES="$(CDPATH='' cd -- "$SCRIPT_DIR/.." && pwd)"
export SHELFFILES="$SHELFFILES"

NIX_HOST_PATH="${SHELFFILES}/nix"

if [ "$(id -u)" -ne 0 ]; then
  echo "Error: This script must be run as root (sudo)." >&2
  exit 1
fi

NAMESPACE_DIR="/run/shelffiles-ns"
mkdir -p "$NAMESPACE_DIR"

NAMESPACE_NAME="shelffiles_$(echo "$SHELFFILES" | tr '/:' '_')"
NAMESPACE_PATH="$NAMESPACE_DIR/$NAMESPACE_NAME"

if [ -e "$NAMESPACE_PATH" ]; then
  echo "Namespace already exists at $NAMESPACE_PATH"
  exit 0
fi

echo "Creating new namespace at $NAMESPACE_PATH"
touch "$NAMESPACE_PATH"

mkdir -p "$NIX_HOST_PATH"

unshare --mount --pid --fork --mount-proc bash -c "
  mount --bind \"$NIX_HOST_PATH\" /nix
  
  echo \$\$ > \"$NAMESPACE_PATH\"
  
  exec tail -f /dev/null
" &

sleep 1

echo "Namespace setup complete at $NAMESPACE_PATH"
echo "You can now use launch_in_namespace.sh to run commands in this namespace"
