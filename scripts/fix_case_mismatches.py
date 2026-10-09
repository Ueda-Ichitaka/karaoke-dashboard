#!/usr/bin/env python3
"""About me: standalone, one-off fixer for UltraStar song files whose name on
disk differs from the name their .txt references (#MP3/#AUDIO/#VIDEO/#COVER/
#BACKGROUND) only in letter case - e.g. the tag says "ABBA - I Have A
Dream.mp3" but the file is "abba - i have a dream.mp3".

Why these exist: the library is reached over an SMB mount (vers=3.0, no Unix
extensions) that the NAS's Samba serves case-insensitively. UltraStar
Manager's rename task rewrites the tag, then asks to rename the file to a
name the share reports as already existing (the same file, other case), so
the file rename is refused. Players over that mount still find the file,
but anything reading the NAS's own case-sensitive disk (the dashboard's
integrity check) does not.

This script renames each such file to the tag's spelling in two steps, via
a temporary name ("<name>.casefix-tmp"), which a case-insensitive share
accepts. It never touches the .txt, never renames a file it can't match
unambiguously, and never overwrites anything.

Lives outside app/ on purpose: the Dockerfile only COPYs app/, so this never
ships in the container image. Stdlib only - run it by hand on the machine
that has the library mounted:

  scripts/fix_case_mismatches.py [--dry-run] [--root <songs-dir>]

--root is the songs directory itself (default: the current directory).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Tags that name a file next to the .txt, the ones UltraStar Manager renames.
FILE_TAGS = ("MP3", "AUDIO", "VIDEO", "COVER", "BACKGROUND")
# Every real UltraStar song file carries these; a .txt without them isn't one.
MANDATORY_TAGS = ("BPM", "GAP")
# Synology system folders and the like, never song folders.
SKIP_PREFIXES = (".", "@", "#")
TEMP_SUFFIX = ".casefix-tmp"


def read_text(path: Path) -> str:
    raw = path.read_bytes()[:2_000_000]
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


def header_tags(text: str) -> dict[str, str]:
    tags: dict[str, str] = {}
    for line in text.splitlines():
        if not line.startswith("#"):
            break
        key, sep, value = line[1:].partition(":")
        if sep:
            tags[key.strip().upper()] = value.strip()
    return tags


def plan_folder(folder: Path, warn) -> list[tuple[str, str]]:
    """(name on disk, tag spelling) pairs to rename in this folder."""
    names = os.listdir(folder)
    by_lower: dict[str, list[str]] = {}
    for name in names:
        by_lower.setdefault(name.lower(), []).append(name)

    wanted: dict[str, set[str]] = {}
    for txt in sorted(n for n in names if n.lower().endswith(".txt")):
        try:
            tags = header_tags(read_text(folder / txt))
        except OSError as err:
            warn(f"skip (unreadable): {folder.name}/{txt}: {err}")
            continue
        if not all(t in tags for t in MANDATORY_TAGS):
            continue
        for tag in FILE_TAGS:
            ref = tags.get(tag)
            if not ref or ref in names or "/" in ref or "\\" in ref:
                continue
            matches = by_lower.get(ref.lower(), [])
            if not matches:
                continue  # really missing, not a case problem
            if len(matches) > 1:
                warn(f"skip (ambiguous, several case variants on disk): {folder.name}/{ref}")
                continue
            wanted.setdefault(matches[0], set()).add(ref)

    plan = []
    for actual, refs in sorted(wanted.items()):
        if len(refs) > 1:
            warn(f"skip (conflict, tags disagree on spelling): {folder.name}/{actual} -> {sorted(refs)}")
            continue
        plan.append((actual, refs.pop()))
    return plan


def rename_two_step(folder: Path, actual: str, target: str) -> None:
    temp = folder / (actual + TEMP_SUFFIX)
    os.rename(folder / actual, temp)
    try:
        os.rename(temp, folder / target)
    except OSError:
        os.rename(temp, folder / actual)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dry-run", action="store_true", help="only print what would be renamed")
    parser.add_argument("--root", default=".", help="the songs directory (default: current directory)")
    args = parser.parse_args(argv)

    root = Path(args.root)
    if not root.is_dir():
        print(f"error: --root '{args.root}' is not a directory", file=sys.stderr)
        return 1

    def warn(message: str) -> None:
        print(message, file=sys.stderr)

    renamed = skipped = failed = 0
    for folder in sorted(root.iterdir()):
        if folder.name.startswith(SKIP_PREFIXES) or not folder.is_dir():
            continue
        try:
            plan = plan_folder(folder, warn)
        except OSError as err:
            warn(f"skip (unreadable folder): {folder.name}: {err}")
            continue
        for actual, target in plan:
            src, dst = f"{folder.name}/{actual}", f"{folder.name}/{target}"
            if os.path.lexists(folder / (actual + TEMP_SUFFIX)):
                warn(f"skip (temporary name already exists): {src}{TEMP_SUFFIX}")
                skipped += 1
                continue
            if args.dry_run:
                print(f"would rename: {src}\n          -> {dst}")
                renamed += 1
                continue
            try:
                rename_two_step(folder, actual, target)
            except OSError as err:
                warn(f"failed: {src} -> {dst}: {err}")
                failed += 1
                continue
            print(f"renamed: {src}\n      -> {dst}")
            renamed += 1

    print()
    if args.dry_run:
        print(f"Dry run: would rename {renamed}, skipped {skipped}.")
    else:
        print(f"Renamed {renamed}, skipped {skipped}, failed {failed}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
