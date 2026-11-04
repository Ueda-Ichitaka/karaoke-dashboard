"""About me: checks UltraStar .txt song files for conformity to the format
spec (https://github.com/UltraStar-Deluxe/format), for the admin integrity
view (which can filter its table by issue kind - issue_kind_counts,
filter_reports). Not a full grammar validator - it catches the deviations
that matter in practice: missing mandatory tags, broken media references, a
missing #VIDEO tag (and a video file in the folder it doesn't reference),
malformed numeric fields, body lines that don't parse as
notes/phrase-breaks/voice changes, and a UTF-8 byte order mark (the spec
wants UTF-8 without one). A .txt with no "#KEY:VALUE" header lines at all
is assumed not to be a song file (e.g. a stray readme) and is silently
skipped, not flagged; the USDX Song Factory's helper files (language.txt,
lyrics.txt, ... - app/ultrastar.py: is_helper_file) are never checked.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .config import settings
from .ultrastar import UTF8_BOM, is_helper_file, parse_header_tags, read_song_text

_MANDATORY_TAGS = ("TITLE", "ARTIST", "BPM")
_FILE_REF_TAGS = ("MP3", "AUDIO", "COVER", "BACKGROUND", "VIDEO")
_NUMERIC_TAGS = ("BPM", "GAP", "START", "END", "YEAR")
# the same list as scripts/repair_library.py
_VIDEO_EXTS = (".mp4", ".mkv", ".avi", ".webm", ".mpg", ".mpeg", ".m4v", ".mov", ".flv", ".divx", ".wmv")
_NUMERIC_RE = re.compile(r"^-?\d+([.,]\d+)?$")
_NOTE_TYPES = (":", "*", "F", "R", "G")


@dataclass(frozen=True, slots=True)
class FormatIssue:
    severity: str  # "error" | "warning"
    message: str
    kind: str  # the issue's type without file/line details, e.g. "#VIDEO file not found"


@dataclass(frozen=True, slots=True)
class FileReport:
    folder: str
    filename: str
    issues: list[FormatIssue] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(i.severity == "error" for i in self.issues)


def _check_mandatory_tags(tags: dict[str, str]) -> list[FormatIssue]:
    issues = []
    for tag in _MANDATORY_TAGS:
        if not tags.get(tag):
            issues.append(FormatIssue("error", f"Missing mandatory #{tag} tag.", f"Missing #{tag}"))
    if not tags.get("MP3") and not tags.get("AUDIO"):
        issues.append(FormatIssue("error", "No audio reference (#MP3 or #AUDIO).", "No audio reference"))
    if not tags.get("VERSION"):
        issues.append(FormatIssue("warning", "Missing #VERSION tag.", "Missing #VERSION"))
    return issues


def _check_numeric_tags(tags: dict[str, str]) -> list[FormatIssue]:
    issues = []
    for tag in _NUMERIC_TAGS:
        value = tags.get(tag)
        if value and not _NUMERIC_RE.match(value):
            issues.append(FormatIssue("warning", f"Malformed #{tag} value: {value!r}.", f"Malformed #{tag}"))
    return issues


def _check_file_references(tags: dict[str, str], folder: Path) -> list[FormatIssue]:
    issues = []
    for tag in _FILE_REF_TAGS:
        name = tags.get(tag)
        if not name:
            continue
        if not (folder / name).is_file():
            issues.append(
                FormatIssue("error", f"Referenced #{tag} file not found: {name!r}.", f"#{tag} file not found")
            )
    return issues


def _check_video_tag(tags: dict[str, str], folder: Path) -> list[FormatIssue]:
    """#VIDEO absent or empty is an error; a video file in the folder makes
    it a second one, naming the videos the tag could point at."""
    if tags.get("VIDEO", "").strip():
        return []
    issues = [FormatIssue("error", "Missing #VIDEO tag.", "Missing #VIDEO")]
    try:
        videos = sorted(p.name for p in folder.iterdir() if p.is_file() and p.suffix.lower() in _VIDEO_EXTS)
    except OSError:
        videos = []
    if videos:
        names = ", ".join(repr(name) for name in videos)
        message = f"A video file is in the folder but not referenced by #VIDEO: {names}."
        issues.append(FormatIssue("error", message, "Video file not referenced"))
    return issues


def _check_body(text: str, tags: dict[str, str]) -> list[FormatIssue]:
    issues = []
    declared_voices = {tag for tag in tags if re.fullmatch(r"P[1-9]", tag)}
    used_voices: set[str] = set()
    note_lines = 0
    in_header = True
    for line in text.splitlines():
        if in_header:
            if line.startswith("#"):
                continue
            in_header = False
        stripped = line.strip()
        if not stripped or stripped == "E":
            continue
        if stripped[0] in _NOTE_TYPES:
            note_lines += 1
        elif stripped[0] == "-":
            continue
        elif re.fullmatch(r"P[1-9]", stripped):
            used_voices.add(stripped)
        else:
            issues.append(
                FormatIssue("warning", f"Unrecognized line in body: {stripped[:40]!r}.", "Unrecognized body line")
            )

    for voice in sorted(used_voices - declared_voices):
        issues.append(FormatIssue(
            "warning", f"Voice change {voice} used without a matching #{voice} header.", "Voice change without header"
        ))

    if note_lines == 0:
        issues.append(FormatIssue("error", "No note lines found - the song has no notes.", "No note lines"))
    return issues


def _check_byte_order_mark(path: Path) -> list[FormatIssue]:
    with path.open("rb") as file:
        if file.read(len(UTF8_BOM)) != UTF8_BOM:
            return []
    return [FormatIssue("warning", "Starts with a UTF-8 byte order mark - the format wants UTF-8 without one.",
                        "Byte order mark")]


def check_file(path: Path) -> FileReport:
    text = read_song_text(path)
    tags = parse_header_tags(text)
    if not tags:
        return FileReport(folder=path.parent.name, filename=path.name)  # not an UltraStar file

    issues = [
        *_check_mandatory_tags(tags),
        *_check_numeric_tags(tags),
        *_check_file_references(tags, path.parent),
        *_check_video_tag(tags, path.parent),
        *_check_body(text, tags),
        *_check_byte_order_mark(path),
    ]
    return FileReport(folder=path.parent.name, filename=path.name, issues=issues)


def _only_missing_version_warning(issues: list[FormatIssue]) -> bool:
    return len(issues) == 1 and issues[0].severity == "warning" and "VERSION" in issues[0].message


def check_library(root: str | Path | None = None) -> list[FileReport]:
    """Every .txt file in the library that has format issues.

    A file whose only issue is the missing-#VERSION warning is left out -
    it's real but non-breaking, and on an older library it would otherwise
    drown out genuine problems.
    """
    base = Path(root if root is not None else settings.songs_dir)
    ignore = set(settings.song_ignore_names)
    reports = []
    try:
        entries = sorted(base.iterdir())
    except OSError:
        return []
    for folder in entries:
        if not folder.is_dir() or folder.name.startswith(".") or folder.name in ignore:
            continue
        for txt_file in sorted(p for p in folder.rglob("*.txt") if not is_helper_file(p.name)):
            report = check_file(txt_file)
            if report.issues and not _only_missing_version_warning(report.issues):
                # Use the path relative to the top-level song folder (not just
                # the immediate parent) so a nested file still points back at
                # the folder shown in the structure report.
                rel_name = str(txt_file.relative_to(folder))
                reports.append(FileReport(folder=folder.name, filename=rel_name, issues=report.issues))
    return reports


def issue_kind_counts(reports: list[FileReport]) -> list[tuple[str, int]]:
    """Each issue kind with how many files have it, most common first."""
    counts: dict[str, int] = {}
    for report in reports:
        for kind in {i.kind for i in report.issues}:
            counts[kind] = counts.get(kind, 0) + 1
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))


def filter_reports(reports: list[FileReport], kind: str) -> list[FileReport]:
    """The files that have an issue of this kind - all of them for ""."""
    if not kind:
        return reports
    return [r for r in reports if any(i.kind == kind for i in r.issues)]
