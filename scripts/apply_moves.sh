#!/usr/bin/env bash
# About me: standalone companion to the karaoke-dashboard admin integrity
# view's "Library structure" and "Misplaced songs" move-list exports
# (app/move_export.py, GET /admin/integrity/non-conforming.moves and
# /admin/integrity/misplaced.moves). UltraStar Manager can point an admin
# at those problems but has no way to actually move a file - this script
# does the real `mv`, reading one or more move-list files: a flat stream
# of NUL-terminated tokens, alternating a source path then its destination
# path (the same convention `find -print0` uses), so no filename, however
# unusual, needs quoting or escaping here.
#
# Lives outside app/ on purpose: the Dockerfile only COPYs app/, so this
# never ships in the container image. Run it by hand, directly against the
# real songs_dir mount.
#
# Usage:
#   scripts/apply_moves.sh [--dry-run] <move-list-file> [more-files...]
#
# For each pair: the destination's parent directory is created if missing,
# then the source is moved into place. A pair is skipped (not an error) and
# reported on stderr when the source is already gone or the destination
# already exists - this script never overwrites anything.

set -uo pipefail

dry_run=0
files=()

for arg in "$@"; do
  case "$arg" in
    --dry-run)
      dry_run=1
      ;;
    -h | --help)
      echo "Usage: $0 [--dry-run] <move-list-file> [more-files...]" >&2
      exit 0
      ;;
    *)
      files+=("$arg")
      ;;
  esac
done

if [ "${#files[@]}" -eq 0 ]; then
  echo "Usage: $0 [--dry-run] <move-list-file> [more-files...]" >&2
  exit 1
fi

for file in "${files[@]}"; do
  if [ ! -r "$file" ]; then
    echo "error: cannot read '$file'" >&2
    exit 1
  fi
done

moved=0
skipped=0
missing=0

for file in "${files[@]}"; do
  while IFS= read -r -d '' src && IFS= read -r -d '' dst; do
    if [ ! -e "$src" ]; then
      echo "skip (source missing): $src" >&2
      missing=$((missing + 1))
      continue
    fi
    if [ -e "$dst" ]; then
      echo "skip (destination already exists): $dst" >&2
      skipped=$((skipped + 1))
      continue
    fi

    if [ "$dry_run" -eq 1 ]; then
      echo "would move: $src -> $dst"
    else
      mkdir -p -- "$(dirname -- "$dst")"
      mv -- "$src" "$dst"
      echo "moved: $src -> $dst"
    fi
    moved=$((moved + 1))
  done <"$file"
done

echo
if [ "$dry_run" -eq 1 ]; then
  echo "Dry run: would move $moved, would skip $skipped, missing source $missing."
else
  echo "Moved $moved, skipped $skipped, missing source $missing."
fi
