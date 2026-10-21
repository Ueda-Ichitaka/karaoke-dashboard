# Library scripts

The dashboard mounts the song library read-only and never changes a file.
The scripts in `scripts/` do: they run by hand against the real songs
directory, outside the container (they aren't part of the image). All of
them have a `--dry-run` mode - use it first.

Run `fix_case_mismatches.py` before `repair_library.py`, which leaves
letter-case mismatches to it.

## Fix letter-case mismatches

```bash
scripts/fix_case_mismatches.py [--dry-run] [--root <songs-dir>]
```

Over an SMB mount without Unix extensions (e.g. `vers=3.0`), the NAS's Samba
matches filenames case-insensitively. When UltraStar Manager renames a file
only in letter case ("abba - i have a dream.mp3" -> "ABBA - I Have A
Dream.mp3"), it rewrites the tag in the `.txt`, but the share reports the new
name as existing and refuses the rename. Players over that mount still find
the file; the integrity check, reading the NAS's case-sensitive disk, doesn't.

The script renames each such file to the tag's spelling via a temporary name,
which the share accepts. It never edits a `.txt`, skips anything ambiguous,
never overwrites a file, and is safe to rerun. Plain Python, standard library
only.

## Repair missing audio/video sources

```bash
scripts/repair_library.py [--dry-run] [--root <songs-dir>] [--csv <file>]
```

Repairs song `.txt` files without a working audio/video source, and writes
what it can't repair as report rows in the `broken.csv` format, ready for
**Reported -> Import CSV** (see [csv.md](csv.md#importing)):

- **Duet next to its solo.** A duet without audio next to a solo whose
  `#BPM` is at most 0.1% and `#GAP` at most 0.6 s apart gets the solo's
  `#MP3`/`#VIDEO` - it's a duet version of the same recording.
- **Other duets without audio** move to their own `<folder> [DUET]` folder
  (with their `.usdb` marker and own images), get copies of the solo's media,
  and a report row (category `other`) asking for re-timing and a `#GAP`
  recalculation, with the intended video from the `.usdb` marker. The own
  folder lets the song factory, which repairs one folder at a time using its
  first song `.txt`, work on it.
- **Missing or dangling `#MP3`/`#VIDEO`** (or an absent `#VIDEO` while a video
  file is present) is set to the only file it can mean: the one named with
  the song's USDB video ID, else the only such file in the folder. A linked
  file starting with `_` loses that `_` unless the plain name is taken.
- **Anything else** - no such file, or several and none identifiable -
  becomes a report row (category `audio` or `video`).

Each song gets one report row: the first problem found sets the category,
every further one is appended to the description as
"Also (<category>): ...". Rows carry what the files state: language
(`#LANGUAGE`, mapped to the dashboard's codes), genre (`#GENRE`, exact code
matches only) and cover link (from the `.usdb` marker).

Before editing a `.txt` the script keeps a `<name>.txt.bak` copy (an existing
one is never overwritten), and it preserves the file's encoding and line
endings. A dry run writes no CSV unless `--csv` is given. Letter-case
mismatches are left to `fix_case_mismatches.py`.

## Apply a move list

```bash
scripts/apply_moves.sh [--dry-run] [--root <songs-dir>] <move-list-file>...
```

The **Integrity** tab's folder-structure and misplaced-songs checks export a
move list (`app/move_export.py`; `non-conforming.moves` and
`misplaced.moves`). Its paths are relative to the library root, which
`--root` names (default: the current directory). The file is a stream of
NUL-terminated paths,
alternating each file's current path and its correct one - the same
convention as `find -print0`. Any character in a filename, even a `/` in a
band name like "AC/DC" (written as "AC-DC" in the destination folder name),
needs no escaping.

The script creates each destination folder as needed and never overwrites an
existing file - it skips and reports that on stderr. A nested subfolder named
`-` (the set-aside folder) is left out of the move list.
