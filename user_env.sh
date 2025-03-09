# Reference: https://wiki.archlinux.org/title/XDG_Base_Directory

## starship
export STARSHIP_CONFIG="$XDG_CONFIG_HOME"/starship.toml
export STARSHIP_CACHE="$XDG_CACHE_HOME"/starship

## zsh
export ZDOTDIR="$XDG_CONFIG_HOME/zsh"

export SHELFFILES_SHELL=zsh
