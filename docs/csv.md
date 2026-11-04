# CSV export and import

The **Reported** and **Requested** tabs export their lists as CSV for the
song pipeline, and import CSV files in the same formats. The Genres page's
**Edit** tab exports genre edits as a tab-separated file
([genre-edits.tsv](#genre-editstsv), export only).

All files are comma-separated, UTF-8, with `\n` row endings and a header row
(unless `CSV_INCLUDE_HEADER=false`). Each tab offers **Export open CSV** and
**Export all CSV**.

## song-requests.csv

Columns:

```
band name, song name, youtube link, language, musicbrainz_id, lyrics_url, cover_url, duet, genre, trait
```

| Column | Content |
| --- | --- |
| `band name`, `song name` | Always set. |
| `youtube link` | Optional. An http(s) link, or - set by a contributor or admin - a filesystem path to an `.mp3` or `.mp4` file. |
| `language` | Optional. ISO 639-1 code or `mixed` (`app/languages.py`). Pins the language detection downstream. |
| `musicbrainz_id` | Optional. The bare ID - a pasted `musicbrainz.org` URL is reduced to it on input (`app/musicbrainz.py`). Enables a direct metadata lookup instead of a fuzzy search. |
| `lyrics_url` | Optional. Tried before an online lyrics search. A genius.com song page (`genius.com/...-lyrics`), an lrclib.net track page (`lrclib.net/tracks/<id>`) or - set by a contributor or admin - a filesystem path to a `.txt` file; nothing else is accepted. |
| `cover_url` | Optional, an http(s) link. |
| `duet` | `yes`, `no`, or blank. Blank appears on older requests and is treated as `no`, here and downstream. |
| `genre` | Set when reviewing (contributors and admins), comma-joined codes from `app/genres.py`, e.g. `metal,gothic`. Never blank: `default` when none is set. |
| `trait` | Set when reviewing (contributors and admins), comma-joined codes from `app/traits.py`, e.g. `harsh_vocals,choir`. Never blank: `none` when none is set. |

The optional columns are consumed by the UltraSinger batch pipeline (see
[UPSTREAM_REQUESTS.md](../UPSTREAM_REQUESTS.md)). The genre and trait lists
keep growing, so expect more codes over time.

## broken.csv

Columns:

```
band, song name, category, description, lyrics_url, language, cover_url, genre, trait
```

| Column | Content |
| --- | --- |
| `band`, `song name` | The song, from its folder name. |
| `category` | One of `gap`, `async`, `lyrics`, `video`, `audio`, `cover`, `other` (`app/broken_categories.py`). |
| `description` | What's wrong. Optional only for `cover`. Cleaned on input (`app/validation.py: sanitize_free_text`): one line, without characters that could break a CSV row or start a spreadsheet formula (commas, semicolons, quotes, a leading `=`/`+`/`-`/`@`, ...). |
| `lyrics_url` | A genius.com song page or an lrclib.net track page, or - set by a contributor or admin - a filesystem path to a `.txt` file. Required for `lyrics` and `async` on the strict form. Stored as `BrokenReport.genius_url`, named `lyrics_url` here to match the pipeline's column. |
| `language` | ISO 639-1 code or `mixed`. Required on the strict form. |
| `cover_url` | Required for `cover`, optional otherwise. |
| `genre`, `trait` | Same as in `song-requests.csv`. |

## Duplicate reports merge

A report for a song that already has a pending or open report doesn't create
a second row (`app/report_matching.py`). Instead:

- the lyrics link and cover link are filled in only if the existing report
  has none;
- the description accumulates: a differing category's label is appended,
  then any new description text;
- the existing report's category, reporter and status stay as they are.

A report for a song whose earlier report is resolved is a new occurrence and
gets its own row.

## Importing

Both tabs have an **Import CSV** button. The file uses the export format of
that tab; the header row is optional, older exports with fewer trailing
columns work, and UTF-8 or Windows-1252 encoding up to 256 KB is accepted.

Every imported row lands in **Needs review**, never directly in the
exportable list, or merges into an existing entry - so a song never appears
twice, and importing the same file twice changes nothing. A row with a
problem is skipped with its line number and the reason; the other rows still
import.

**Merge rules** (`app/import_merge.py`, shared by both imports):

- a field the existing entry lacks is filled in;
- an lrclib.net lyrics link wins over any other; otherwise the existing link
  stays;
- genres and traits are combined (`default`/`none` only stand alone);
- a description is appended unless it's already contained;
- any other differing value keeps the existing one and is listed under the
  import result as a note to check.

### Reports (`app/report_import.py`)

- The song is found by an exact `band - song name` folder match
  (case-insensitive). A row is skipped if there's no such folder.
- A row merges into the song's pending or open report, or into an earlier row
  of the same file. A differing category is added to the description; a
  differing language or cover link is listed.
- A song whose only report is resolved is skipped.
- A row is skipped if a value isn't valid: category, language, genre or trait
  codes, a cover link that isn't http(s), or a lyrics link that isn't a
  genius.com song page, an lrclib.net track page or a `.txt` path.
- Imported reports still need a language and lyrics link before they can be
  admitted.

### Requests (`app/request_import.py`)

- A row merges into the pending or open request with the same band, song and
  duet setting (the public form's duplicate check), or into an earlier row of
  the same file. A differing YouTube link, language, MusicBrainz ID or cover
  link is listed.
- A row is skipped if the song is already in the library (exact
  `band - song` folder), if the same request is already done, or if a value
  fails the request form's own checks.

## genre-edits.tsv

**Export N edits** on the Genres page's Edit tab (contributors and admins,
`/genres/edit/export.tsv`) downloads every open genre edit for the USDX Song
Factory, which writes the genres into the song files (`factory.sh
pull-genres`, then `factory.sh genres`). There is no import.

- UTF-8, `\n` line endings, no header, one line per song file:
  the file's path relative to the library root, a tab, the genres.
- Only song files count - a `.txt` with `#BPM` directly in the song folder.
  The Factory's helper files (`language.txt`, `lyrics.txt`, `song_end.txt`,
  `anchors.txt`) never appear. A folder with two song files gets two lines.
- The genres are comma-separated as the Edit tab saved them, e.g.
  `Symphonic, Metal`.
- An edit stays in the export until a library scan reads the same genres
  from the song files; exporting twice gives the same file.

```
Nightwish - Nemo/Nightwish - Nemo.txt	Symphonic, Metal
AC-DC - Hells Bells/HellsBells-638.txt	Rock, Hard
```
