# Reference: https://wiki.archlinux.org/title/XDG_Base_Directory

## starship
export STARSHIP_CONFIG="$XDG_CONFIG_HOME"/starship.toml
export STARSHIP_CACHE="$XDG_CACHE_HOME"/starship

## npm
export NPM_CONFIG_USERCONFIG="$XDG_CONFIG_HOME/npm/npmrc"
export PATH="$XDG_DATA_HOME/npm/bin:$PATH"

## claude
export CLAUDE_CONFIG_DIR="$XDG_CONFIG_HOME/claude"

# deno
export DENO_INSTALL_ROOT="$XDG_DATA_HOME/deno/bin"
export PATH="$DENO_INSTALL_ROOT:$PATH"

## codex
export CODEX_HOME="$XDG_CONFIG_HOME/codex"

## zsh
export ZDOTDIR="$XDG_CONFIG_HOME/zsh"
# Workaround for vscode shell integration
export USER_ZDOTDIR="$XDG_CONFIG_HOME/zsh"
