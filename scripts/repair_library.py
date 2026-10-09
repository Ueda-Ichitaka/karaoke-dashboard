#!/usr/bin/env python3
"""About me: standalone, one-off repair for UltraStar songs whose .txt has no
working audio/video source, and the report list for what it can't repair.

Per song .txt (a .txt with #BPM and #GAP) in each song folder under --root:

  A. A duet (#P1/#P2 or #DUETSINGERP1/P2) without audio, next to a solo
     sibling whose #BPM is at most 0.1% and #GAP at most 0.6 s apart: it's a
     duet version of the solo's recording - it gets the solo's #MP3/#VIDEO.
  B. Any other duet without audio next to a solo with audio: it was timed to
     a different recording. It moves to its own "<folder> [DUET]" folder
     (with its .usdb marker and its own cover/background images), gets
     copies of the solo's audio/video, and a report row (category "other")
     asking for re-timing and a #GAP recalculation.
  C. A missing or dangling audio tag, or a dangling or absent video tag, is
     set to the file it can only mean: the one whose name contains the
     song's USDB video ID (from its .usdb marker), else the only audio
     (video) file in the folder. A duet whose intended video is present is
     linked this way rather than moved. A linked file whose name starts with
     "_" (set aside by hand) loses that "_", unless the plain name is already
     taken in the folder (ignoring letter case, as the SMB share does).
  D. Nothing to link (no such file, or several and none identifiable): a
     report row (category "audio"/"video") instead of a guess.

Report rows go to a CSV in the karaoke-dashboard's broken.csv format, for
its "Import CSV" on the Reported page - one row per song, as the dashboard
reports a song only once: the first repair found sets the category, every
further one is appended to the description ("Also (<category>): ..."). Each row carries what the files
state explicitly: language (#LANGUAGE), genre (#GENRE, exact matches to the
dashboard's codes only), cover link (.usdb), intended video (.usdb, in the
description). A song with no #VIDEO tag and no video file is audio-only and
fine; a case-only name mismatch is left to scripts/fix_case_mismatches.py.

Safety: never overwrites or deletes a file, copies a .txt to "<name>.bak"
(once - an existing .bak is kept) before editing it, keeps its encoding and
line endings, and skips anything ambiguous with a reason on stderr.

Lives outside app/ on purpose: the Dockerfile only COPYs app/, so this never
ships in the container image. Stdlib only - run it by hand on the machine
that has the library mounted:

  scripts/repair_library.py [--dry-run] [--root <songs-dir>] [--csv <file>]

--root is the songs directory itself (default: the current directory).
--csv is where the report rows go (default: library-repair.csv in the
current directory); a dry run writes no CSV unless --csv is given.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

AUDIO_EXTS = (".mp3", ".ogg", ".m4a", ".wav", ".flac", ".opus", ".aac")
VIDEO_EXTS = (".mp4", ".mkv", ".avi", ".webm", ".mpg", ".mpeg", ".m4v", ".mov", ".flv", ".divx", ".wmv")
AUDIO_TAGS = ("MP3", "AUDIO")
IMAGE_TAGS = ("COVER", "BACKGROUND")
SKIP_PREFIXES = (".", "@", "#")
SEPARATOR = " - "
GAP_TOLERANCE_MS = 600
BPM_TOLERANCE = 0.001  # relative
DUET_SUFFIX = " [DUET]"
DEFAULT_CSV = "library-repair.csv"
CSV_COLUMNS = ("band", "song name", "category", "description", "lyrics_url", "language", "cover_url", "genre", "trait")

# The dashboard's language codes by English name (app/languages.py - a test
# keeps these in sync), plus spellings the real library uses.
LANGUAGES = {
    "german": "de", "english": "en", "french": "fr", "spanish": "es", "italian": "it", "portuguese": "pt",
    "dutch": "nl", "polish": "pl", "russian": "ru", "swedish": "sv", "danish": "da", "norwegian": "no",
    "finnish": "fi", "turkish": "tr", "japanese": "ja", "korean": "ko", "chinese": "zh",
    "englisch": "en", "deutsch": "de", "español": "es", "espanol": "es",
}
# The dashboard's genre codes by code and label (app/genres.py - a test
# keeps these in sync). Exact matches only.
GENRES = {
    "metal": "metal", "medieval": "medieval", "folk": "folk", "gothic": "gothic", "symphonic": "symphonic",
    "punk": "punk", "pop": "pop", "rap": "rap", "kpop": "kpop", "k-pop": "kpop", "jpop": "jpop",
    "j-pop": "jpop", "rock": "rock", "industrial": "industrial", "ebm": "ebm",
}


def map_language(raw: str) -> str:
    parts = [p.strip() for p in re.split(r"[,/;&]", raw) if p.strip()]
    if len(parts) > 1:
        return "mixed"
    if not parts:
        return ""
    key = re.sub(r"\s*\(romani[sz]ed\)\s*$", "", parts[0], flags=re.IGNORECASE).casefold()
    return LANGUAGES.get(key, "")


def map_genres(raw: str) -> str:
    codes: list[str] = []
    for part in re.split(r"[,/]", raw):
        code = GENRES.get(part.strip().casefold())
        if code and code not in codes:
            codes.append(code)
    return ",".join(codes) if codes else "default"


def _number(raw: str | None) -> float | None:
    try:
        return float((raw or "").strip().replace(",", "."))
    except ValueError:
        return None


@dataclass
class Song:
    name: str
    tags: dict[str, str]
    usdb_ids: list[str] = field(default_factory=list)
    usdb_cover: str = ""
    usdb_file: str | None = None

    @property
    def is_duet(self) -> bool:
        return any(self.tags.get(t) for t in ("P1", "P2", "DUETSINGERP1", "DUETSINGERP2"))


@dataclass
class Move:
    folder: Path
    duet: Song
    dest: Path
    moves: list[str]
    copies: list[str]
    changes: list[tuple[str, str]]


@dataclass
class Plan:
    renames: list[tuple[str, str]] = field(default_factory=list)
    edits: list[tuple[Path, list[tuple[str, str]]]] = field(default_factory=list)
    moves: list[Move] = field(default_factory=list)
    rows: list[dict[str, str]] = field(default_factory=list)


def read_text(path: Path) -> tuple[str, str, bool]:
    raw = path.read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    try:
        return raw.decode("utf-8-sig"), "utf-8", bom
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace"), "cp1252", bom


def header_tags(text: str) -> dict[str, str]:
    tags: dict[str, str] = {}
    for line in text.splitlines():
        if not line.startswith("#"):
            break
        key, sep, value = line[1:].partition(":")
        if sep:
            tags[key.strip().upper()] = value.strip()
    return tags


def edit_tags(path: Path, changes: list[tuple[str, str]]) -> None:
    """Sets each tag (replacing its value, or inserting it before #BPM)."""
    raw = path.read_bytes()
    text, encoding, bom = read_text(path)
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(newline)
    header_end = next((i for i, line in enumerate(lines) if not line.startswith("#")), len(lines))

    def key(line: str) -> str:
        return line[1:].partition(":")[0].strip().upper()

    for tag, value in changes:
        index = next((i for i in range(header_end) if key(lines[i]) == tag), None)
        if index is not None:
            lines[index] = lines[index][: lines[index].index(":") + 1] + value
            continue
        bpm = next((i for i in range(header_end) if key(lines[i]) == "BPM"), header_end)
        lines.insert(bpm, f"#{tag}:{value}")
        header_end += 1

    data = newline.join(lines).encode(encoding)
    if bom:
        data = b"\xef\xbb\xbf" + data
    backup = path.with_name(path.name + ".bak")
    if not os.path.lexists(backup):
        backup.write_bytes(raw)
    path.write_bytes(data)


def _usdb_markers(folder: Path, names: list[str]) -> dict[str, tuple[list[str], str, str]]:
    """txt filename -> (YouTube IDs, cover link, .usdb filename)."""
    markers = {}
    for name in names:
        if not name.lower().endswith(".usdb"):
            continue
        try:
            data = json.loads((folder / name).read_text(encoding="utf-8"))
            txt = data["txt"]["fname"]
        except (OSError, ValueError, KeyError, TypeError):
            continue
        ids = re.findall(r"(?:^|,)\s*[va]=([^,\s]+)", data.get("meta_tags") or "")
        cover = (data.get("cover") or {}).get("resource") or ""
        markers[txt] = (ids, cover if cover.startswith(("http://", "https://")) else "", name)
    return markers


class FolderPlanner:
    def __init__(self, folder: Path, warn):
        self.folder = folder
        self.warn = warn
        self.names = sorted(os.listdir(folder))
        self.files = {n for n in self.names if (folder / n).is_file()}
        self.audio = [n for n in self.names if n in self.files and n.lower().endswith(AUDIO_EXTS)]
        self.video = [n for n in self.names if n in self.files and n.lower().endswith(VIDEO_EXTS)]
        markers = _usdb_markers(folder, self.names)
        self.songs: list[Song] = []
        for name in self.names:
            if name not in self.files or not name.lower().endswith(".txt"):
                continue
            try:
                tags = header_tags(read_text(folder / name)[0])
            except OSError as err:
                warn(f"skip (unreadable): {folder.name}/{name}: {err}")
                continue
            if "BPM" in tags and "GAP" in tags:
                ids, cover, usdb = markers.get(name, ([], "", None))
                self.songs.append(Song(name, tags, ids, cover, usdb))
        self.effective: dict[str, tuple[str | None, str | None]] = {}
        self.renamed: dict[str, str] = {}

    def _linked_name(self, pick: str, plan: Plan) -> str:
        """The name a picked file is linked under - without a leading "_"
        unless that name is taken (case-insensitively)."""
        if pick in self.renamed:
            return self.renamed[pick]
        if not pick.startswith("_") or len(pick) == 1:
            return pick
        plain = pick[1:]
        taken = {n.lower() for n in self.names} | {n.lower() for n in self.renamed.values()}
        if plain.lower() in taken:
            return pick
        self.renamed[pick] = plain
        plan.renames.append((pick, plain))
        return plain

    # -- state of a song's sources --------------------------------------
    def _case_variant(self, ref: str) -> bool:
        return ref not in self.files and any(f.lower() == ref.lower() for f in self.files)

    def audio_state(self, song: Song) -> tuple[str, str | None]:
        refs = [song.tags[t] for t in AUDIO_TAGS if song.tags.get(t)]
        for ref in refs:
            if ref in self.files:
                return "ok", ref
        if any(self._case_variant(r) for r in refs):
            return "case", refs[0]
        return "missing", refs[0] if refs else None

    def video_state(self, song: Song) -> tuple[str, str | None]:
        ref = song.tags.get("VIDEO")
        if not ref:
            return "none", None
        if ref in self.files:
            return "ok", ref
        if self._case_variant(ref):
            return "case", ref
        return "missing", ref

    def _pick(self, candidates: list[str], ids: list[str]) -> tuple[str | None, bool]:
        """(the file it can only mean, whether several were in the running)."""
        by_id = [c for c in candidates if any(i in c for i in ids)]
        if len(by_id) == 1:
            return by_id[0], False
        if len(candidates) == 1:
            return candidates[0], False
        return None, len(candidates) > 1

    # -- planning --------------------------------------------------------
    def row(self, song: Song, category: str, description: str, folder_name: str | None = None) -> dict[str, str]:
        band, sep, title = (folder_name or self.folder.name).partition(SEPARATOR)
        if not sep:
            band, title = "", band
        return {
            "band": band.strip(), "song name": title.strip(), "category": category,
            "description": description.replace(",", "").replace(";", "").replace('"', ""),
            "lyrics_url": "", "language": map_language(song.tags.get("LANGUAGE", "")),
            "cover_url": song.usdb_cover, "genre": map_genres(song.tags.get("GENRE", "")), "trait": "none",
        }

    def _audio_changes(self, song: Song, value: str) -> list[tuple[str, str]]:
        present = [t for t in AUDIO_TAGS if song.tags.get(t)]
        return [(t, value) for t in (present or ["MP3"])]

    def plan_links(self, song: Song, plan: Plan, audio: bool = True) -> None:
        """Group C/D: link a missing source to its file, or report it."""
        changes: list[tuple[str, str]] = []
        audio_value = None
        rel = f"{self.folder.name}/{song.name}"
        if audio:
            state, ref = self.audio_state(song)
            if state == "case":
                self.warn(f"skip (letter-case mismatch - run fix_case_mismatches.py first): {rel} #MP3:{ref}")
            elif state == "missing":
                pick, several = self._pick(self.audio, song.usdb_ids)
                if pick:
                    audio_value = self._linked_name(pick, plan)
                    changes += self._audio_changes(song, audio_value)
                elif several:
                    plan.rows.append(self.row(song, "audio", (
                        f"Several audio files in the folder and none identified as the one for {song.name} "
                        f"({' / '.join(self.audio)}) - set its #MP3 to the right one."
                    )))
                else:
                    was = f"#MP3 points to the missing {ref}" if ref else "no #MP3 tag"
                    plan.rows.append(self.row(song, "audio", f"No audio file in the folder for {song.name} ({was})."))
            else:
                audio_value = ref
        state, ref = self.video_state(song)
        video_value = ref if state == "ok" else None
        if state == "case":
            self.warn(f"skip (letter-case mismatch - run fix_case_mismatches.py first): {rel} #VIDEO:{ref}")
        elif state in ("none", "missing") and (self.video or state == "missing"):
            pick, several = self._pick(self.video, song.usdb_ids)
            if pick:
                video_value = self._linked_name(pick, plan)
                changes.append(("VIDEO", video_value))
            elif state == "missing" and several:
                plan.rows.append(self.row(song, "video", (
                    f"Several video files in the folder and none identified as the one for {song.name} "
                    f"({' / '.join(self.video)}) - set its #VIDEO to the right one."
                )))
            elif state == "missing":
                plan.rows.append(self.row(
                    song, "video", f"No video file in the folder for {song.name} (#VIDEO points to the missing {ref})."
                ))
        if changes:
            plan.edits.append((self.folder / song.name, changes))
        self.effective[song.name] = (audio_value, video_value)

    def plan_duet(self, duet: Song, solos: list[Song], plan: Plan) -> None:
        state, _ = self.audio_state(duet)
        intended = [a for a in self.audio if any(i in a for i in duet.usdb_ids)]
        if state != "missing" or len(intended) == 1:
            self.plan_links(duet, plan)
            return
        with_audio = [s for s in solos if self.effective.get(s.name, (None, None))[0]]
        timed = [s for s in with_audio if self._same_timing(duet, s)]
        if len(timed) == 1:  # group A
            audio, video = self.effective[timed[0].name]
            changes = self._audio_changes(duet, audio)
            if video and self.video_state(duet)[0] != "ok":
                changes.append(("VIDEO", video))
            plan.edits.append((self.folder / duet.name, changes))
            return
        if len(with_audio) != 1:
            self.plan_links(duet, plan)
            return
        self.plan_move(duet, with_audio[0], solos, plan)  # group B

    def _same_timing(self, duet: Song, solo: Song) -> bool:
        bpm_d, bpm_s = _number(duet.tags.get("BPM")), _number(solo.tags.get("BPM"))
        gap_d, gap_s = _number(duet.tags.get("GAP")), _number(solo.tags.get("GAP"))
        if None in (bpm_d, bpm_s, gap_d, gap_s):
            return False
        return abs(bpm_d - bpm_s) <= BPM_TOLERANCE * abs(bpm_s) and abs(gap_d - gap_s) <= GAP_TOLERANCE_MS

    def plan_move(self, duet: Song, solo: Song, solos: list[Song], plan: Plan) -> None:
        rel = f"{self.folder.name}/{duet.name}"
        if self.folder.name.lower().endswith(DUET_SUFFIX.strip().lower()):
            self.warn(f"skip (folder is already a [DUET] folder): {rel}")
            return
        dest = self.folder.parent / (self.folder.name + DUET_SUFFIX)
        if os.path.lexists(dest):
            self.warn(f"skip (destination already exists): {dest.name}/ for {rel}")
            return
        others = {v for s in self.songs if s is not duet for t, v in s.tags.items() if t in IMAGE_TAGS}
        moves = [duet.name] + ([duet.usdb_file] if duet.usdb_file else [])
        copies: list[str] = []
        for tag in IMAGE_TAGS:
            image = duet.tags.get(tag)
            if image and image in self.files and image not in moves + copies:
                (copies if image in others else moves).append(image)
        audio, video = self.effective[solo.name]
        copies += [audio] + ([video] if video else [])
        changes = self._audio_changes(duet, audio) + ([("VIDEO", video)] if video else [])
        plan.moves.append(Move(self.folder, duet, dest, moves, copies, changes))

        def fmt(tag: str, song: Song) -> str:
            return (song.tags.get(tag) or "?").replace(",", ".")

        description = (
            f"Duet moved out of the solo folder into its own. Its chart is timed to a different recording "
            f"than the solo media copied here (BPM {fmt('BPM', duet)} vs {fmt('BPM', solo)} - "
            f"GAP {fmt('GAP', duet)} vs {fmt('GAP', solo)} ms) - it has to be re-timed against this media "
            f"and #GAP recalculated."
        )
        video_ids = [i for i in duet.usdb_ids if i]
        if video_ids:
            description += f" Intended video: https://www.youtube.com/watch?v={video_ids[0]}"
        plan.rows.append(self.row(duet, "other", description, folder_name=dest.name))

    def plan(self) -> Plan:
        plan = Plan()
        solos = [s for s in self.songs if not s.is_duet]
        for song in solos:
            self.plan_links(song, plan)
        for song in self.songs:
            if song.is_duet:
                self.plan_duet(song, solos, plan)
        return plan


def merge_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """One row per song (the dashboard reports a song only once): the first
    row keeps its category, every further repair for the same song is
    appended to its description, and blank fields fill in from later rows.
    Songs are matched case-insensitively, like the dashboard's import."""
    merged: dict[tuple[str, str], dict[str, str]] = {}
    for row in rows:
        key = (row["band"].casefold(), row["song name"].casefold())
        first = merged.get(key)
        if first is None:
            merged[key] = dict(row)
            continue
        first["description"] += f" Also ({row['category']}): {row['description']}"
        for name in ("lyrics_url", "language", "cover_url"):
            if not first[name]:
                first[name] = row[name]
        if first["genre"] == "default":
            first["genre"] = row["genre"]
    return list(merged.values())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dry-run", action="store_true", help="only print what would be done")
    parser.add_argument("--root", default=".", help="the songs directory (default: current directory)")
    parser.add_argument("--csv", help=f"report rows output (default: {DEFAULT_CSV}; none in a dry run)")
    args = parser.parse_args(argv)

    root = Path(args.root)
    if not root.is_dir():
        print(f"error: --root '{args.root}' is not a directory", file=sys.stderr)
        return 1

    def warn(message: str) -> None:
        print(message, file=sys.stderr)

    verb = "would " if args.dry_run else ""
    counts = {"edited": 0, "renamed": 0, "moved": 0, "failed": 0}
    rows: list[dict[str, str]] = []
    for folder in sorted(root.iterdir()):
        if folder.name.startswith(SKIP_PREFIXES) or not folder.is_dir():
            continue
        try:
            plan = FolderPlanner(folder, warn).plan()
        except OSError as err:
            warn(f"skip (unreadable folder): {folder.name}: {err}")
            continue
        rows += plan.rows

        not_renamed: set[str] = set()
        for old, new in plan.renames:
            print(f"{verb}rename: {folder.name}/{old} -> {new}")
            if not args.dry_run:
                try:
                    if os.path.lexists(folder / new):
                        raise FileExistsError(f"{new} already exists")
                    os.rename(folder / old, folder / new)
                except OSError as err:
                    warn(f"failed: renaming {folder.name}/{old}: {err}")
                    counts["failed"] += 1
                    not_renamed.add(new)
                    continue
            counts["renamed"] += 1

        for path, changes in plan.edits:
            for tag, value in changes:
                print(f"{verb}set #{tag} in {folder.name}/{path.name}: {value}")
            if any(value in not_renamed for _, value in changes):
                warn(f"skip (its file could not be renamed): {folder.name}/{path.name}")
                continue
            if not args.dry_run:
                try:
                    edit_tags(path, changes)
                except (OSError, UnicodeEncodeError) as err:
                    warn(f"failed: {folder.name}/{path.name}: {err}")
                    counts["failed"] += 1
                    continue
            counts["edited"] += 1

        for move in plan.moves:
            for name in move.moves:
                print(f"{verb}move: {folder.name}/{name} -> {move.dest.name}/{name}")
            for name in move.copies:
                print(f"{verb}copy: {folder.name}/{name} -> {move.dest.name}/{name}")
            for tag, value in move.changes:
                print(f"{verb}set #{tag} in {move.dest.name}/{move.duet.name}: {value}")
            if not args.dry_run:
                try:
                    move.dest.mkdir()
                    for name in move.copies:
                        shutil.copy2(folder / name, move.dest / name)
                    for name in move.moves:
                        os.rename(folder / name, move.dest / name)
                    edit_tags(move.dest / move.duet.name, move.changes)
                except (OSError, UnicodeEncodeError) as err:
                    warn(f"failed: moving {folder.name}/{move.duet.name} to {move.dest.name}/: {err}")
                    counts["failed"] += 1
                    continue
            counts["moved"] += 1

    rows = merge_rows(rows)
    for row in rows:
        print(f"{verb}report: {row['band']} - {row['song name']} | {row['category']} | {row['description']}")

    csv_path = args.csv or (None if args.dry_run else DEFAULT_CSV)
    if csv_path:
        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)

    print()
    if args.dry_run:
        done = (f"Dry run: would edit {counts['edited']} song files, would rename {counts['renamed']} files, "
                f"would move {counts['moved']} duets")
    else:
        done = f"Edited {counts['edited']} song files, renamed {counts['renamed']} files, moved {counts['moved']} duets"
    print(f"{done}, {len(rows)} report rows{f' -> {csv_path}' if csv_path else ''}, failed {counts['failed']}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
