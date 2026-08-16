#!/usr/bin/env bats

setup() {
  repo_root="$(CDPATH='' cd -- "$BATS_TEST_DIRNAME" && pwd -P)"
  while [ ! -d "$repo_root/entrypoint" ] && [ "$repo_root" != / ]; do
    repo_root="$(dirname -- "$repo_root")"
  done
  [ -d "$repo_root/entrypoint" ]
  test_root="$(mktemp -d /tmp/shelffiles-portable-test.XXXXXX)"
  checkout="$test_root/checkout"
  fake_bin="$test_root/bin"
  fixed_alias_token="shelffiles-portable-test-${BATS_TEST_NUMBER}-$$"
  mkdir -p "$checkout" "$fake_bin"
  cp -a "$repo_root/entrypoint" "$repo_root/portable" "$repo_root/utils" "$checkout/"
}

teardown() {
  if [ -L /tmp/impac ]; then
    alias_target="$(readlink /tmp/impac)"
    case "$alias_target" in
      "$checkout/portable/nix/store"|"/tmp/$fixed_alias_token-wrong")
        rm -- /tmp/impac
        ;;
    esac
  elif [ -f /tmp/impac ] && [ "$(cat /tmp/impac 2>/dev/null)" = "$fixed_alias_token" ]; then
    rm -- /tmp/impac
  elif [ -d /tmp/impac ] && [ -f "/tmp/impac/$fixed_alias_token" ]; then
    rm -- "/tmp/impac/$fixed_alias_token"
    rmdir /tmp/impac
  fi

  if [ -n "${result_path:-}" ] || [ -n "${dependency_path:-}" ]; then
    chmod -R u+w -- "${result_path:-/nonexistent}" \
      "${dependency_path:-/nonexistent}" 2>/dev/null || true
    rm -rf -- "${result_path:-/nonexistent}" "${dependency_path:-/nonexistent}"
  fi
  chmod -R u+w -- "$test_root" 2>/dev/null || true
  rm -rf -- "$test_root"
}

require_writable_nix_store() {
  mkdir -p /nix/store 2>/dev/null || skip 'requires an isolated writable /nix/store (provided by test/Dockerfile)'
  [ -w /nix/store ] || skip 'requires an isolated writable /nix/store (provided by test/Dockerfile)'
}

create_export_fixture() {
  unique="${BATS_TEST_NUMBER}-$$"
  result_path="/nix/store/00000000000000000000000000000000-shelffiles-test-$unique"
  dependency_path="/nix/store/11111111111111111111111111111111-dependency-test-$unique"
  export FAKE_RESULT_PATH="$result_path"
  export FAKE_DEPENDENCY_PATH="$dependency_path"

  mkdir -p "$result_path/bin" "$dependency_path/lib"
  printf 'binary-prefix\0/nix/store\0binary-suffix\n' >"$dependency_path/lib/value"
  # shellcheck disable=SC2016
  printf '#!/bin/sh\nprintf "SHELL=%%s\\nPATH=%%s\\nSHELFFILES=%%s\\nSHELFFILES_ENV_FILE=%%s\\n" "$(basename "$0")" "$PATH" "$SHELFFILES" "${SHELFFILES_ENV_FILE-unset}"\n' \
    >"$result_path/bin/shell-template"
  chmod 0755 "$result_path/bin/shell-template"
  for shell_name in bash fish zsh; do
    cp -a "$result_path/bin/shell-template" "$result_path/bin/$shell_name"
  done
  ln -s "$dependency_path/lib/value" "$result_path/dependency-link"
  chmod -R a-w "$result_path" "$dependency_path"
  ln -s "$result_path" "$checkout/result"

  cat >"$fake_bin/nix-store" <<'EOF'
#!/bin/sh
if [ "$1" != --query ] || [ "$2" != --requisites ] || [ "$3" != "$FAKE_RESULT_PATH" ]; then
  printf 'unexpected nix-store invocation\n' >&2
  exit 2
fi
printf '%s\n' "$FAKE_DEPENDENCY_PATH" "$FAKE_RESULT_PATH"
EOF
  chmod 0755 "$fake_bin/nix-store"
}

donor_digest() {
  {
    find "$result_path" "$dependency_path" -type f -exec sha256sum {} \;
    find "$result_path" "$dependency_path" -type l -exec sh -c \
      'for link do printf "%s -> %s\\n" "$link" "$(readlink "$link")"; done' sh {} +
  } | LC_ALL=C sort | sha256sum
}

@test "export rewrites a small closure without changing its donor" {
  require_writable_nix_store
  create_export_fixture
  donor_before="$(donor_digest)"
  printf 'keep entrypoint\n' >"$checkout/portable/entrypoint/sentinel"
  printf 'keep outside\n' >"$checkout/outside-sentinel"

  run env PATH="$fake_bin:$PATH" "$checkout/utils/create_portable.sh"
  echo "$output"
  [ "$status" -eq 0 ]
  [[ "$output" == *"Closure paths copied: 2"* ]]
  [ "$(donor_digest)" = "$donor_before" ]

  copied_result="$checkout/portable/nix/store/${result_path##*/}"
  copied_dependency="$checkout/portable/nix/store/${dependency_path##*/}"
  grep -aFq /tmp/impac "$copied_dependency/lib/value"
  run grep -aFq /nix/store "$copied_dependency/lib/value"
  [ "$status" -ne 0 ]
  [ "$(readlink "$copied_result/dependency-link")" = "/tmp/impac/${dependency_path##*/}/lib/value" ]
  [ -x "$copied_result/bin/bash" ]
  [ "$(readlink "$checkout/portable/result")" = "nix/store/${result_path##*/}" ]
  [[ "$(readlink "$checkout/portable/result")" != /* ]]

  chmod -R u+w "$checkout/portable/nix"
  touch "$checkout/portable/nix/discard-on-regeneration"
  run env PATH="$fake_bin:$PATH" "$checkout/utils/create_portable.sh"
  [ "$status" -eq 0 ]
  [ ! -e "$checkout/portable/nix/discard-on-regeneration" ]
  [ -f "$checkout/portable/entrypoint/sentinel" ]
  [ -f "$checkout/outside-sentinel" ]
  [ "$(donor_digest)" = "$donor_before" ]
}

@test "residual source references fail before portable result is created" {
  require_writable_nix_store
  create_export_fixture
  donor_before="$(donor_digest)"
  cat >"$fake_bin/sed" <<'EOF'
#!/bin/sh
# Fault injection: report success without replacing bytes.
exit 0
EOF
  chmod 0755 "$fake_bin/sed"

  run env PATH="$fake_bin:$PATH" "$checkout/utils/create_portable.sh"
  echo "$output"
  [ "$status" -ne 0 ]
  [[ "$output" == *"Residual regular-file reference"* ]]
  [[ "$output" == *"residual /nix/store references remain"* ]]
  [ ! -e "$checkout/portable/result" ]
  [ ! -L "$checkout/portable/result" ]
  [ "$(donor_digest)" = "$donor_before" ]
}

@test "ordinary entrypoints stay ordinary and portable wrappers select portable PATH" {
  require_writable_nix_store
  create_export_fixture
  run env PATH="$fake_bin:$PATH" "$checkout/utils/create_portable.sh"
  [ "$status" -eq 0 ]

  for shell_name in bash fish zsh; do
    run env PATH="$fake_bin:$PATH" "$checkout/entrypoint/$shell_name"
    echo "$output"
    [ "$status" -eq 0 ]
    [[ "$output" == *":$checkout/result/bin:"* ]]
    [[ "$output" != *"$checkout/portable/result/bin"* ]]
  done

  if [ -e /tmp/impac ] || [ -L /tmp/impac ]; then
    skip 'pre-existing /tmp/impac is left untouched'
  fi
  expected_store="$checkout/portable/nix/store"
  for shell_name in bash fish zsh; do
    run env PATH="$fake_bin:$PATH" "$checkout/portable/entrypoint/$shell_name"
    echo "$output"
    [ "$status" -eq 0 ]
    [ "$(readlink /tmp/impac)" = "$expected_store" ]
    [[ "$output" == *"PATH=$checkout/portable/result/bin:"* ]]
    [[ "$output" == *":$checkout/result/bin:"* ]]
    [[ "$output" == *"SHELFFILES_ENV_FILE=unset"* ]]
  done

  rm -- /tmp/impac
  ln -s "/tmp/$fixed_alias_token-wrong" /tmp/impac
  run env PATH="$fake_bin:$PATH" "$checkout/portable/entrypoint/bash"
  echo "$output"
  [ "$status" -eq 73 ]
  [ "$(readlink /tmp/impac)" = "/tmp/$fixed_alias_token-wrong" ]
  rm -- /tmp/impac

  printf %s "$fixed_alias_token" >/tmp/impac
  run env PATH="$fake_bin:$PATH" "$checkout/portable/entrypoint/bash"
  [ "$status" -eq 73 ]
  [ "$(cat /tmp/impac)" = "$fixed_alias_token" ]
  rm -- /tmp/impac

  mkdir /tmp/impac
  touch "/tmp/impac/$fixed_alias_token"
  run env PATH="$fake_bin:$PATH" "$checkout/portable/entrypoint/bash"
  [ "$status" -eq 73 ]
  [ -f "/tmp/impac/$fixed_alias_token" ]
}

@test "ordinary entrypoints continue when ordinary user environment returns nonzero" {
  require_writable_nix_store
  create_export_fixture
  printf 'return 42\n' >"$checkout/user_env.sh"

  for shell_name in bash fish zsh; do
    run env PATH="$fake_bin:$PATH" "$checkout/entrypoint/$shell_name"
    echo "$output"
    [ "$status" -eq 0 ]
    [[ "$output" == *"SHELL=$shell_name"* ]]
    [[ "$output" == *"SHELFFILES_ENV_FILE=unset"* ]]
  done
}

@test "portable wrappers reject a missing broken or misplaced result before launch" {
  require_writable_nix_store
  create_export_fixture
  run env PATH="$fake_bin:$PATH" "$checkout/utils/create_portable.sh"
  [ "$status" -eq 0 ]

  if [ -e /tmp/impac ] || [ -L /tmp/impac ]; then
    skip 'pre-existing /tmp/impac is left untouched'
  fi

  rm -- "$checkout/portable/result"
  run env PATH="$fake_bin:$PATH" "$checkout/portable/entrypoint/bash"
  echo "$output"
  [ "$status" -ne 0 ]
  [[ "$output" == *"Portable result is missing or broken"* ]]
  [[ "$output" != *"SHELL=bash"* ]]
  [ ! -e /tmp/impac ]
  [ ! -L /tmp/impac ]

  ln -s nix/store/missing-result "$checkout/portable/result"
  run env PATH="$fake_bin:$PATH" "$checkout/portable/entrypoint/bash"
  [ "$status" -ne 0 ]
  [[ "$output" == *"Portable result is missing or broken"* ]]
  [[ "$output" != *"SHELL=bash"* ]]
  [ ! -e /tmp/impac ]
  [ ! -L /tmp/impac ]

  rm -- "$checkout/portable/result"
  ln -s ../result "$checkout/portable/result"
  run env PATH="$fake_bin:$PATH" "$checkout/portable/entrypoint/bash"
  echo "$output"
  [ "$status" -ne 0 ]
  [[ "$output" == *"Portable result resolves outside the portable store"* ]]
  [[ "$output" != *"SHELL=bash"* ]]
  [ ! -e /tmp/impac ]
  [ ! -L /tmp/impac ]
}
