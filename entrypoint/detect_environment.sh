#!/bin/bash

set -eu

SCRIPT_DIR="$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)"
SHELFFILES="$(CDPATH='' cd -- "$SCRIPT_DIR/.." && pwd)"
export SHELFFILES="$SHELFFILES"

if command -v nix &> /dev/null; then
    echo "Nix is already installed."
    NIX_INSTALLED=1
else
    echo "Nix is not installed."
    NIX_INSTALLED=0
fi

if [ "$(id -u)" -eq 0 ] || sudo -n true 2>/dev/null; then
    echo "Root access is available."
    ROOT_ACCESS=1
else
    echo "Root access is not available."
    ROOT_ACCESS=0
fi

if [ -w /nix ] 2>/dev/null || [ ! -e /nix ] && [ "$ROOT_ACCESS" -eq 1 ]; then
    echo "/nix is writable or can be created."
    NIX_WRITABLE=1
else
    echo "/nix is not writable."
    NIX_WRITABLE=0
fi

if command -v bwrap &> /dev/null; then
    echo "Bubblewrap is available."
    BWRAP_AVAILABLE=1
else
    echo "Bubblewrap is not available."
    BWRAP_AVAILABLE=0
fi

NAMESPACE_DIR="/run/shelffiles-ns"
NAMESPACE_NAME="shelffiles_$(echo "$SHELFFILES" | tr '/:' '_')"
NAMESPACE_PATH="$NAMESPACE_DIR/$NAMESPACE_NAME"

if [ -e "$NAMESPACE_PATH" ]; then
    echo "Namespace is already set up."
    NAMESPACE_SETUP=1
else
    echo "Namespace is not set up."
    NAMESPACE_SETUP=0
fi

if [ "$NIX_INSTALLED" -eq 1 ] && [ "$NIX_WRITABLE" -eq 1 ]; then
    echo "Recommended mode: Direct Nix build"
    RECOMMENDED_MODE="direct"
elif [ "$ROOT_ACCESS" -eq 1 ] && [ "$NIX_WRITABLE" -eq 0 ]; then
    if [ "$NAMESPACE_SETUP" -eq 1 ]; then
        echo "Recommended mode: Namespace with nsenter"
        RECOMMENDED_MODE="namespace"
    else
        echo "Recommended mode: Namespace (needs setup with 'sudo $SCRIPT_DIR/setup_namespace.sh')"
        RECOMMENDED_MODE="namespace_setup"
    fi
elif [ "$BWRAP_AVAILABLE" -eq 1 ]; then
    echo "Recommended mode: Bubblewrap"
    RECOMMENDED_MODE="bwrap"
else
    echo "Recommended mode: Install nix-portable"
    RECOMMENDED_MODE="nix-portable"
fi

cat << EOF
NIX_INSTALLED=$NIX_INSTALLED
ROOT_ACCESS=$ROOT_ACCESS
NIX_WRITABLE=$NIX_WRITABLE
BWRAP_AVAILABLE=$BWRAP_AVAILABLE
NAMESPACE_SETUP=$NAMESPACE_SETUP
RECOMMENDED_MODE="$RECOMMENDED_MODE"
EOF
