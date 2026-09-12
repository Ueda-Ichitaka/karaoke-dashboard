"""About me: checks UltraStar .txt song files for conformity to the format
spec (https://github.com/UltraStar-Deluxe/format), for the admin integrity
view. Not a full grammar validator - it catches the deviations that matter
in practice: missing mandatory tags, broken media references, malformed
numeric fields, and body lines that don't parse as notes/phrase-breaks/voice
changes. A .txt with no "#KEY:VALUE" header lines at all is assumed not to
be a song file (e.g. a stray readme) and is silently skipped, not flagged.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .config import settings
from .ultrastar import parse_header_tags, read_song_text

_MANDATORY_TAGS = ("TITLE", "ARTIST", "BPM")
_FILE_REF_TAGS = ("MP3", "AUDIO", "COVER", "BACKGROUND", "VIDEO")
_NUMERIC_TAGS = ("BPM", "GAP", "START", "END", "YEAR")
_NUMERIC_RE = re.compile(r"^-?\d+([.,]\d+)?$")
_NOTE_TYPES = (":", "*", "F", "R", "G")


@dataclass(frozen=True, slots=True)
class FormatIssue:
    severity: str  # "error" | "warning"
    message: str


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
            issues.append(FormatIssue("error", f"Missing mandatory #{tag} tag."))
    if not tags.get("MP3") and not tags.get("AUDIO"):
        issues.append(FormatIssue("error", "No audio reference (#MP3 or #AUDIO)."))
    if not tags.get("VERSION"):
        issues.append(FormatIssue("warning", "Missing #VERSION tag."))
    return issues


def _check_numeric_tags(tags: dict[str, str]) -> list[FormatIssue]:
    issues = []
    for tag in _NUMERIC_TAGS:
        value = tags.get(tag)
        if value and not _NUMERIC_RE.match(value):
            issues.append(FormatIssue("warning", f"Malformed #{tag} value: {value!r}."))
    return issues


def _check_file_references(tags: dict[str, str], folder: Path) -> list[FormatIssue]:
    issues = []
    for tag in _FILE_REF_TAGS:
        name = tags.get(tag)
        if not name:
            continue
        if not (folder / name).is_file():
            issues.append(FormatIssue("error", f"Referenced #{tag} file not found: {name!r}."))
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
            issues.append(FormatIssue("warning", f"Unrecognized line in body: {stripped[:40]!r}."))

    for voice in sorted(used_voices - declared_voices):
        issues.append(FormatIssue("warning", f"Voice change {voice} used without a matching #{voice} header."))

    if note_lines == 0:
        issues.append(FormatIssue("error", "No note lines found - the song has no notes."))
    return issues


def check_file(path: Path) -> FileReport:
    text = read_song_text(path)
    tags = parse_header_tags(text)
    if not tags:
        return FileReport(folder=path.parent.name, filename=path.name)  # not an UltraStar file

    issues = [
        *_check_mandatory_tags(tags),
        *_check_numeric_tags(tags),
        *_check_file_references(tags, path.parent),
        *_check_body(text, tags),
    ]
    return FileReport(folder=path.parent.name, filename=path.name, issues=issues)


def check_library(root: str | Path | None = None) -> list[FileReport]:
    """Every .txt file in the library that has format issues."""
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
        for txt_file in sorted(folder.rglob("*.txt")):
            report = check_file(txt_file)
            if report.issues:
                # Use the path relative to the top-level song folder (not just
                # the immediate parent) so a nested file still points back at
                # the folder shown in the structure report.
                rel_name = str(txt_file.relative_to(folder))
                reports.append(FileReport(folder=folder.name, filename=rel_name, issues=report.issues))
    return reports
