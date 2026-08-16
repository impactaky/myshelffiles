# shellcheck shell=sh

# This file is selected by the portable wrappers through SHELFFILES_ENV_FILE.
# Load the ordinary environment first so config, state, and XDG behavior remain
# shared with the normal entrypoints.
PORTABLE_ENTRYPOINT_DIR="$(
  CDPATH='' cd -- "$(dirname -- "${shelffiles_env_file:?portable environment file is not set}")" && pwd -P
)"
PORTABLE_ROOT="$(CDPATH='' cd -- "$PORTABLE_ENTRYPOINT_DIR/../.." && pwd -P)"

# shellcheck disable=SC1091
. "$PORTABLE_ROOT/entrypoint/env.sh"

ensure_portable_alias() {
  alias_path=$1
  expected_store=$2

  if [ -L "$alias_path" ]; then
    actual_store="$(readlink "$alias_path")"
    if [ "$actual_store" = "$expected_store" ]; then
      return 0
    fi
    printf 'Portable alias conflict: %s points to %s; expected %s\n' \
      "$alias_path" "$actual_store" "$expected_store" >&2
    return 73
  fi

  if [ -e "$alias_path" ]; then
    printf 'Portable alias conflict: %s exists and is not a symlink\n' \
      "$alias_path" >&2
    return 73
  fi

  if ln -s "$expected_store" "$alias_path" 2>/dev/null; then
    return 0
  fi

  # A concurrent creator may have won the race. Accept only the exact target.
  if [ -L "$alias_path" ]; then
    actual_store="$(readlink "$alias_path")"
    if [ "$actual_store" = "$expected_store" ]; then
      return 0
    fi
    printf 'Portable alias conflict: %s points to %s; expected %s\n' \
      "$alias_path" "$actual_store" "$expected_store" >&2
    return 73
  fi
  if [ -e "$alias_path" ]; then
    printf 'Portable alias conflict: %s exists and is not a symlink\n' \
      "$alias_path" >&2
    return 73
  fi

  printf 'Could not create portable alias %s -> %s\n' \
    "$alias_path" "$expected_store" >&2
  return 1
}

activate_portable_environment() {
  alias_path=$1
  expected_store=$2
  portable_result=$3

  ensure_portable_alias "$alias_path" "$expected_store" || return $?
  export PATH="$portable_result/bin:$PATH"
}

PORTABLE_STORE="$(CDPATH='' cd -- "$PORTABLE_ROOT/portable/nix/store" 2>/dev/null && pwd -P)" || {
  printf 'Portable store is missing. Run utils/create_portable.sh first.\n' >&2
  return 1
}
PORTABLE_RESULT="$PORTABLE_ROOT/portable/result"
PORTABLE_RESULT_RESOLVED="$(CDPATH='' cd -- "$PORTABLE_RESULT" 2>/dev/null && pwd -P)" || {
  printf 'Portable result is missing or broken. Run utils/create_portable.sh first.\n' >&2
  return 1
}
case "$PORTABLE_RESULT_RESOLVED" in
  "$PORTABLE_STORE"/*) ;;
  *)
    printf 'Portable result resolves outside the portable store: %s\n' \
      "$PORTABLE_RESULT_RESOLVED" >&2
    return 1
    ;;
esac

activate_portable_environment \
  /tmp/impac "$PORTABLE_STORE" "$PORTABLE_RESULT" || {
  portable_status=$?
  return "$portable_status"
}
