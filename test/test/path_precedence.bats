#!/usr/bin/env bats

setup() {
  repo_root="$(CDPATH='' cd -- "$BATS_TEST_DIRNAME" && pwd)"
  # Walk up until we find the repo root that contains entrypoint/.
  while [ ! -d "$repo_root/entrypoint" ] && [ "$repo_root" != / ]; do
    repo_root="$(dirname -- "$repo_root")"
  done
  user_id="$(id -u)"
  group_id="$(id -g)"
  path_id="$(printf '%s\n' "${repo_root}_${user_id}_${group_id}" | tr '/:' '__')"
  expected_shims="$repo_root/share/$path_id/glolias/shims"
}

@test "entrypoint/bash puts XDG data glolias shims before result bins in PATH" {
  run ./entrypoint/bash -i -c 'printf "PATH=%s\n" "$PATH"'

  echo "Status: $status"
  echo "Output: $output"

  [ "$status" -eq 0 ]
  [[ "$output" == *"PATH=$expected_shims:$repo_root/result/bin:$repo_root/result_docker/bin:"* ]]
}
