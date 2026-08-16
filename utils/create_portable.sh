#!/usr/bin/env bash
set -euo pipefail

# Export the already-built result closure into a runtime-only relocated copy.
# This script intentionally has no build step and never writes to /nix/store.

readonly source_prefix=/nix/store
readonly runtime_prefix=/tmp/impac
script_dir="$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly script_dir
checkout_root="$(CDPATH='' cd -- "$script_dir/.." && pwd -P)"
readonly checkout_root
readonly source_result="$checkout_root/result"
readonly portable_root="$checkout_root/portable"
readonly portable_nix="$portable_root/nix"
readonly portable_store="$portable_nix/store"
readonly portable_result="$portable_root/result"

fail() {
  printf 'Portable export failed: %s\n' "$1" >&2
  exit 1
}

cleanup_generated_path() {
  local path=$1
  case "$path" in
    "$portable_nix")
      if [[ -e "$path" || -L "$path" ]]; then
        chmod -R u+w -- "$path" 2>/dev/null || true
        rm -rf -- "$path"
      fi
      ;;
    "$portable_result")
      rm -rf -- "$path"
      ;;
    *)
      fail "refusing to remove unexpected path: $path"
      ;;
  esac
}

for tool in chmod cp dirname find grep ln mkdir mktemp readlink rm sed sort stat uname wc; do
  command -v "$tool" >/dev/null 2>&1 || fail "required command is missing: $tool"
done

[[ "$(uname -s)" == Linux ]] || fail 'only Linux is supported'
source_bytes="$(LC_ALL=C printf %s "$source_prefix" | wc -c)"
runtime_bytes="$(LC_ALL=C printf %s "$runtime_prefix" | wc -c)"
[[ "$source_bytes" == "$runtime_bytes" ]] || \
  fail "prefixes must have equal byte lengths ($source_bytes != $runtime_bytes)"

[[ -e "$source_result" ]] || fail "ordinary result is missing: $source_result"
resolved_result="$(readlink -f -- "$source_result")" || \
  fail "could not resolve ordinary result: $source_result"
[[ "$resolved_result" == "$source_prefix/"* ]] || \
  fail "ordinary result must resolve under $source_prefix: $resolved_result"
[[ -d "$resolved_result" ]] || fail "resolved ordinary result is not a directory: $resolved_result"
result_name="${resolved_result##*/}"
[[ "$result_name" =~ ^[0123456789abcdfghijklmnpqrsvwxyz]{32}-.+ ]] || \
  fail "ordinary result is not a Nix store path: $resolved_result"

if command -v nix-store >/dev/null 2>&1; then
  nix_store="$(command -v nix-store)"
elif [[ -x "$source_result/bin/nix-store" ]]; then
  nix_store="$source_result/bin/nix-store"
else
  fail 'nix-store is unavailable (install Nix or include nix-store in result)'
fi
readonly nix_store

closure_inventory="$(mktemp /tmp/shelffiles-portable-closure.XXXXXX)"
readonly closure_inventory
trap 'rm -f -- "$closure_inventory"' EXIT

LC_ALL=C "$nix_store" --query --requisites "$resolved_result" \
  | LC_ALL=C sort -u >"$closure_inventory" || fail 'could not query result closure'
[[ -s "$closure_inventory" ]] || fail 'nix-store returned an empty closure'

result_in_closure=0
while IFS= read -r store_path; do
  [[ -n "$store_path" ]] || fail 'closure contains an empty path'
  [[ "$(dirname -- "$store_path")" == "$source_prefix" ]] || \
    fail "closure contains a path outside $source_prefix: $store_path"
  store_name="${store_path##*/}"
  [[ "$store_name" =~ ^[0123456789abcdfghijklmnpqrsvwxyz]{32}-.+ ]] || \
    fail "closure contains a non-Nix store path: $store_path"
  [[ -e "$store_path" || -L "$store_path" ]] || \
    fail "closure path is missing: $store_path"
  [[ "$store_path" == "$resolved_result" ]] && result_in_closure=1
done <"$closure_inventory"
[[ "$result_in_closure" == 1 ]] || fail 'queried closure does not contain the ordinary result'

# Regeneration is deliberately destructive, but only for these two generated
# paths. The tracked portable/entrypoint layer is never inside either target.
mkdir -p -- "$portable_root"
cleanup_generated_path "$portable_result"
cleanup_generated_path "$portable_nix"
mkdir -p -- "$portable_store"

closure_count=0
while IFS= read -r store_path; do
  cp -a --no-preserve=ownership -- "$store_path" "$portable_store/"
  ((closure_count += 1))
done <"$closure_inventory"

regular_files_rewritten=0
regular_references_rewritten=0
while IFS= read -r -d '' file_path; do
  if ! LC_ALL=C grep -aFq -- "$source_prefix" "$file_path"; then
    continue
  fi

  reference_count="$(LC_ALL=C grep -aobF -- "$source_prefix" "$file_path" | wc -l || true)"
  file_mode="$(stat -c %a -- "$file_path")"
  parent_dir="$(dirname -- "$file_path")"
  parent_mode="$(stat -c %a -- "$parent_dir")"
  chmod u+w -- "$parent_dir" "$file_path"
  LC_ALL=C sed -i "s|$source_prefix|$runtime_prefix|g" "$file_path"
  chmod "$file_mode" -- "$file_path"
  chmod "$parent_mode" -- "$parent_dir"
  ((regular_files_rewritten += 1))
  ((regular_references_rewritten += reference_count))
done < <(find "$portable_store" -type f -print0)

symlinks_rewritten=0
while IFS= read -r -d '' link_path; do
  link_target="$(readlink -- "$link_path")"
  [[ "$link_target" == *"$source_prefix"* ]] || continue
  replacement="${link_target//$source_prefix/$runtime_prefix}"
  parent_dir="$(dirname -- "$link_path")"
  parent_mode="$(stat -c %a -- "$parent_dir")"
  chmod u+w -- "$parent_dir"
  ln -sfn -- "$replacement" "$link_path"
  chmod "$parent_mode" -- "$parent_dir"
  ((symlinks_rewritten += 1))
done < <(find "$portable_store" -type l -print0)

residual_regular=0
while IFS= read -r -d '' file_path; do
  if LC_ALL=C grep -aFq -- "$source_prefix" "$file_path"; then
    printf 'Residual regular-file reference: %s\n' "$file_path" >&2
    ((residual_regular += 1))
  fi
done < <(find "$portable_store" -type f -print0)

residual_symlinks=0
while IFS= read -r -d '' link_path; do
  link_target="$(readlink -- "$link_path")"
  if [[ "$link_target" == *"$source_prefix"* ]]; then
    printf 'Residual symlink reference: %s -> %s\n' "$link_path" "$link_target" >&2
    ((residual_symlinks += 1))
  fi
done < <(find "$portable_store" -type l -print0)

if ((residual_regular != 0 || residual_symlinks != 0)); then
  fail "residual $source_prefix references remain (files=$residual_regular, symlinks=$residual_symlinks)"
fi

copied_result="$portable_store/$result_name"
[[ -d "$copied_result" ]] || fail "transformed result is missing: $copied_result"
chmod -R a-w -- "$portable_nix"
ln -s "nix/store/$result_name" "$portable_result"

printf 'Portable export complete\n'
printf '  Result: %s -> %s\n' "$portable_result" "$(readlink "$portable_result")"
printf '  Closure paths copied: %s\n' "$closure_count"
printf '  Regular files rewritten: %s (%s references)\n' \
  "$regular_files_rewritten" "$regular_references_rewritten"
printf '  Symlink targets rewritten: %s\n' "$symlinks_rewritten"
printf '  Runtime prefix: %s\n' "$runtime_prefix"
