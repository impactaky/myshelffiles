# Reference: https://wiki.archlinux.org/title/XDG_Base_Directory

## starship
export STARSHIP_CONFIG="$XDG_CONFIG_HOME"/starship.toml
export STARSHIP_CACHE="$XDG_CACHE_HOME"/starship

## npm
export NPM_CONFIG_USERCONFIG=$XDG_CONFIG_HOME/npm/npmrc
export PATH="$XDG_CONFIG_DATA_HOME/npm/bin:$PATH"
