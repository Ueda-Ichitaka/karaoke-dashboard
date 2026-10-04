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
# Both paths in a move-list file are RELATIVE to the library's own root
# (e.g. "Artist - Title/song.txt"), never absolute - the dashboard's own
# songs_dir is just where its container happens to have the library
# mounted, which has nothing to do with where this script runs. --root (or
# the current directory, if omitted) tells this script where that root
# actually is here.
#
# Lives outside app/ on purpose: the Dockerfile only COPYs app/, so this
# never ships in the container image. Run it by hand, directly against the
# real library on its host.
#
# Usage:
#   scripts/apply_moves.sh [--dry-run] [--root <dir>] <move-list-file> [more-files...]
#
# For each pair: the destination's parent directory is created if missing,
# then the source is moved into place. A pair is skipped (not an error) and
# reported on stderr when the source is already gone or the destination
# already exists - this script never overwrites anything.

set -uo pipefail

usage() {
  echo "Usage: $0 [--dry-run] [--root <dir>] <move-list-file> [more-files...]" >&2
}

dry_run=0
root="."
files=()

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run)
      dry_run=1
      shift
      ;;
    --root)
      if [ $# -lt 2 ]; then
        echo "error: --root needs a directory argument" >&2
        exit 1
      fi
      # Strip any trailing slash(es) so "$root/$rel_path" below never ends
      # up with a doubled "//". Root "/" itself is normalized to "" instead
      # of being stripped away entirely, so "$root/$rel_path" still comes
      # out as "/$rel_path" rather than "//$rel_path".
      root="$2"
      while [ "${root: -1}" = "/" ]; do
        root="${root%/}"
      done
      shift 2
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      files+=("$1")
      shift
      ;;
  esac
done

if [ "${#files[@]}" -eq 0 ]; then
  usage
  exit 1
fi

if [ ! -d "${root:-/}" ]; then
  echo "error: --root '${root:-/}' is not a directory" >&2
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
  while IFS= read -r -d '' rel_src && IFS= read -r -d '' rel_dst; do
    src="$root/$rel_src"
    dst="$root/$rel_dst"

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
