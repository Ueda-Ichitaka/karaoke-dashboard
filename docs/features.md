# Features

Every page of Karaoke Dashboard in detail. There are three levels of user:
a plain **user**, a **contributor** - who also gets Reported, Requested,
Duplicates and the genre Edit tab - and an **admin**, who gets everything
(see [Users](#users)). For the CSV formats and imports
see [csv.md](csv.md); for the scripts that change files on disk see
[library-scripts.md](library-scripts.md).

| Tab | Who | What |
| --- | --- | --- |
| [Songs](#songs) | everyone | Browse and search the library |
| [What's new](#whats-new) | everyone | Songs recently added and recently updated |
| [Genres](#genres) | logged-in users | The library by genre: list, map and genre connections; contributors also edit genres |
| [Report broken](#report-broken) | logged-in users | Report a broken song |
| [Request song](#request-song) | logged-in users | Ask for a new song |
| [Reported](#reported-and-requested) | contributors, admins | Review, edit, resolve and export broken-song reports |
| [Requested](#reported-and-requested) | contributors, admins | Review, edit, close and export song requests |
| [Duplicates](#duplicates) | contributors, admins | Songs that exist more than once |
| [Integrity](#integrity) | admins | Format, folder structure and misplaced-song checks |
| [Users](#users) | admins | Accounts |
| [Settings](#settings) | admins | Form profiles, app mode, logging, badge mode, library scan, genres on the map |

## Songs

The song list is the set of sub-folders of the mounted songs directory, one
entry per folder, split into artist and title on `" - "`
(`SONG_SEPARATOR`). Synology system folders (`@eaDir`, `#recycle`, ...) and
dot-folders are ignored. The search filters live as you type and works
without JavaScript too.

**Song details.** Click a row to expand it: every UltraStar `.txt` file in
that folder is parsed into a metadata card - cover, length, duet, genre,
year, language. A folder can hold several distinct songs (batch-imported
folders often do), and each gets its own card. The length comes from the
audio/video file the song plays (`#AUDIO`/`#MP3`/`#VIDEO`), not from the
rarely present `#START`/`#END` tags. The expansion is a native `<details>`
element, no JavaScript involved.

**Reported broken badge** (`app/known_broken.py`). A song with a report that
is still awaiting review, or an admitted report that is still open, carries
a red **Reported broken** badge, for guests too - here and on
[What's new](#whats-new). Hovering it shows the report categories. A
resolved report doesn't count. Whether a fix to the song also removes the
badge is a [setting](#settings).

## What's new

Two panels side by side (`app/library_history.py`): **Recently added** and
**Recently updated** list the songs added and the songs updated within the
[What's new period](#settings) (2 months by default), newest first, with the
date and the Reported broken badge. The search bar on top narrows both lists, live as you type. Below
760px the panels stack. Each entry links to that song in the song library.

The library has no "added" or "updated" date of its own, so a background
scan records what it finds (table `library_folders`). It runs once at app
start and then on the schedule set on the [Settings](#settings) page, by
default daily at 11:00; the page only reads its results. Admins can also
run it, or reset it, from [Settings](#settings). The same scan reads each
song's genres for the [Genres](#genres) page.

- **The very first scan** counts every folder as old, for both lists. They
  start empty and fill with what happens afterwards.
- **Added**: a folder the scan hasn't seen before is a new song, dated by
  that scan. It's listed once it follows the library convention - an
  `Artist - Title` name and no nested subfolder, the same rule as the
  Integrity structure check. Renaming a folder makes it a new folder to the
  scan.
- **Updated**: a write to a `.txt`, `.mp3` or `.opus` file directly in a
  song folder - a changed write time or size, or a new file - is an update,
  dated by that file's write time. A copy that keeps the original file time
  carries that older time. Deleting a file, or writing any other file type,
  is not an update.
- **Grace period**: writes within 1 hour after a new folder was first seen
  count as part of adding it (files still being copied in), not as updates.

## Genres

The library by genre, for logged-in users (the tab is shown to everyone; a
visitor is sent to the login page). The tabs share one head - the song
counts, the search bar and the tab row **List | Map | Connections**, plus
**Edit** for contributors and admins; the tab links keep the search.

### List

`/genres`. Two parts side by side, stacked below 760px:

- **Genre list** (left): every genre of the library with its number of
  songs, most songs first, with a bar relative to the biggest genre.
  **All genres** on top lists every song with a genre.
- **Songs** (right): the songs of the picked genre, as band and title with
  the song's genres as chips. A chip opens that genre; the song opens it
  on the Songs page. For a picked genre, "Often together with" names the
  three genres its songs share most. The list is paged like the Songs page.

The search bar on top narrows both by band, title and genre, live as you
type, and keeps the picked genre.

### Map

`/genres/map`. Every song with a genre is one dot, in the circle of its
first shown genre in the song file; inside it, the dot leans towards the
circles of the song's next three shown genres, so songs that also are
Heavy gather on the side facing Heavy. Genres that share many songs sit
close together - touching at most, circles never overlap - and genres that
share none keep some space between them. A circle's size follows the dots
inside it; its label counts every song with the genre, as the List tab
does. The biggest genres get a cluster each -
as many as **Genres on the map** on [Settings](#settings), 12 by default; the
songs whose genres are all smaller gather in a grey **Other genres** cluster,
and the genres folded into it are listed below the map. The first 12
clusters have a colour of their own, the rest are grey.

- A search marks the matching dots and dims the rest ("7 songs match").
- Hovering a dot shows band, title and genres; clicking it opens a song
  card with the genres as chips and a link to the song on the Songs page
  (without JavaScript the dot is that link).
- A cluster, its label or its chip in the legend opens the genre on the List tab.
- The songs without a genre are counted below the map.

### Connections

`/genres/connections`. A tile per shown genre - song count, a bar relative
to the biggest genre, its three biggest bands - and one for **Other genres**
naming the first eight folded genres. Below, the network: a circle per
genre with its name inside, a line per pair of genres that songs share (thicker for more songs)
with those songs as dots on it (a song with three genres is on three
lines), and the songs with one genre as dots around their circle. Search,
hover, song card and links work as on the Map.

Both drawings are SVG computed on the server (`app/genre_layout.py`): the
same library always gives the same picture. Both are spread out wide (2:1,
the shape of the page) and fill the page width.

### Edit

`/genres/edit`, for contributors and admins: every song - also those
without a genre - paged like the Songs page, with its genres in a text
field. The search narrows by band, title and genre; **Only edited** shows
just the songs with an open edit.

- A row shows its genres as text; **Edit** opens the field, **Save** stores
  it in place, **Cancel** or Escape puts the old value back. Without
  JavaScript every field is open and Save reloads the page at the same
  search and page.
- The field suggests the genres already in the library, for the genre being
  typed (after the last comma), so spellings stay the same.
- The text is split like a `#GENRE` tag - at commas, trimmed, placeholders
  and repeats dropped, runs of white space made one space. An empty field,
  or one with only placeholders, is refused ("Enter at least one genre.").
- An edited row is marked and names the genres its song file has;
  **Reset** drops the edit. Saving the file's own genres drops it too.
- An edit shows on every tab at once - List, Map and Connections use the
  edited genres. It ends by itself when a [library scan](#whats-new) reads
  the same genres (same order, any case) from the song files.
- **Export N edits** downloads `genre-edits.tsv` for the USDX Song
  Factory: every open edit, one line per `.txt` file directly in the song
  folder - the file's path relative to the library root, a tab, the genres
  (`Nightwish - Nemo/Nightwish - Nemo.txt<TAB>Symphonic, Metal`). No
  header; exporting again gives the same file until scans end the edits.

Edits are stored in the table `genre_edits` (`app/song_genres.py`).

### Where the genres come from

The genres come from the `#GENRE` tag of the song files (`app/song_genres.py`),
read by the [library scan](#whats-new) on every run and stored in the table
`song_genres`, so the page is as fresh as the last scan (**Scan now** on
[Settings](#settings) reads them right away).

- The USDX Song Factory writes normalised genres (`Symphonic, Metal`), so a
  value is only split at commas and trimmed. A genre named twice in any
  case counts once, in its first spelling.
- Empty tags and the Factory's placeholders for "no genre" - Unknown, No
  idea, Other, None, Misc (any case) - are skipped; such a song isn't on the
  page.
- A folder with several song files has the genres of all of them.
- Only `.txt` files directly in a song folder count, as for the song details.

The admin genre lists of the request and report forms
(`app/genres.py`) are separate and not used here.

## Report broken

Pick a song, choose a category and describe what's broken. The categories
(`app/broken_categories.py`):

| Code | Label |
| --- | --- |
| `gap` | #GAP (song starts too early/late) |
| `async` | Song goes out of sync |
| `lyrics` | Lyrics broken |
| `video` | Missing video |
| `audio` | Missing audio |
| `cover` | Wrong or missing cover image |
| `other` | Other |

Song, category and description are always required - except for `cover`,
which requires a cover image link instead, since there's nothing to
describe. What else is required depends on the form's profile (see
[Settings](#settings)):

- **strict**: the language too, and for `lyrics`/`async` a lyrics link.

The lyrics link, whenever given, must be a genius.com song page
(`genius.com/...-lyrics`) or an lrclib.net track page
(`lrclib.net/tracks/...`) - the pages the song pipeline can use.
- **karaoke night**: nothing beyond song, category and description (or the
  cover link).

A report for a song that already has a pending or open report is merged into
it instead of creating a second one - see
[csv.md](csv.md#duplicate-reports-merge). Submissions land in **Needs
review**, not in the exportable list.

## Request song

Band and title are always required. The other fields:

- **YouTube link, language, lyrics link** - required under **strict**,
  optional under **karaoke night**. The lyrics link must be a genius.com
  song page or an lrclib.net track page, as on the report form.
- **MusicBrainz ID** - always optional. A pasted `musicbrainz.org` URL is
  reduced to the bare ID (`app/musicbrainz.py`).
- **Cover image link** - always optional, must be http(s).
- **Duet** - is a duet version wanted? Defaults to "No".

A request is refused if the song is already in the library (exact
`band - song` folder, case-insensitive) or already has a request, pending or
admitted, with the same Duet setting. A plain and a duet request for the same
song can exist side by side. Submissions land in **Needs review**.

## Reported and Requested

Both tabs work the same way, for contributors and admins alike - including
status changes, discarding, deleting, the CSV import and the export.

**Needs review.** Newly submitted reports and requests aren't exportable
yet. Edit one to fill in anything missing, then **Admit** it into the
exportable list, or **Discard** it. The edit form's **Save and admit** button
saves first and then admits; if the admit check still finds something
missing, you stay on the form with the error shown.

A report in Needs review also has **Resolved**, for an issue that's already
fixed or not worth admitting: it goes straight to the admitted list as
resolved, without the admit check, keeping when it was submitted. It shows
under **All**, is in **Export all CSV** and can be reopened. A new report for
the song through the form is a new report; the CSV import skips a song whose
only report is resolved.

**Genre and trait** (`app/genres.py`, `app/traits.py`) are review-only tags,
set by contributors and admins, never on the public forms. A song can have several genres (e.g. `metal`,
`gothic`) and several vocal/instrument traits (e.g. `harsh_vocals`, `choir`).
They default to "Default"/"None" and show in their own table columns.
Checking a trait unchecks "None", and checking "None" clears the traits.

**What admitting requires.** The review Edit form and **Admit** use their own
fixed rules, independent of the public form's profile, so switching a
profile never changes what a reviewer must fill in:

- **Reports**: a language and a lyrics link for every category, plus the
  category's own rule (a description, or a cover image link for `cover`).
- **Lyrics links** on both: a genius.com song page, an lrclib.net track page,
  or a filesystem path to a `.txt` lyrics file you prepared yourself - here
  and in the CSV imports, never on the public forms.
- **Requests**: YouTube link, language, MusicBrainz ID and lyrics link. The
  YouTube field also takes a filesystem path to an `.mp3` or `.mp4` file you
  prepared yourself - here and in the CSV import, never on the public form. In
  production mode, a request for a song that's already in the library (exact
  folder match) can't be admitted - switch to debug mode to admit it anyway.

**The exportable lists.** Reports can be edited, resolved and exported as
`broken.csv`; requests can be edited, closed, deleted and exported as
`song-requests.csv`, and show whether they already match a library folder.
Each tab exports open entries only or all of them, and imports a CSV in the
same format. See [csv.md](csv.md).

**Updated since report.** A report - in **Needs review** as well as
admitted - is marked **Updated since report** in its *Song files* column when the library scan (see
[What's new](#whats-new)) read a write to the song's `.txt`, `.mp3` or
`.opus` files that is newer than the report - a sign the song was fixed, so you can
check it and resolve the report. Hovering shows when the files were
written. What counts is when the report was first submitted, not when it
was admitted. Some older reports store their admit time instead of the
submission time; for those, the admit time counts. Every scan, the very
first included, reads each file's write time, so a fix written before the
scan's first run counts too. The mark is as fresh as the last scan - **Scan
now** on the Settings page refreshes it.

## Duplicates

Three sections, with a sidebar to jump between them (`app/duplicates.py`):

- **Duplicates** - songs that appear more than once with the same artist and
  title, across folders and within one folder (e.g. two differently named
  `.txt` charts side by side). Each group's page shows every copy's
  folder/filename and a field-by-field comparison (genre, year, language,
  length, cover, ...).
- **Possible duplicates (versions)** - titles that only differ in a
  `(...)`/`[...]` aside or punctuation, like "Skyfall" and "Skyfall (Full
  Length)". These are often kept on purpose.
- **Folders without a song** - folders with no UltraStar song file (empty,
  or media only), except the set-aside folder `-`. A `.txt` counts as a song
  file when it has `#BPM`, the one mandatory tag a song can't play without
  (`#GAP` is optional in the [format spec](https://usdx.eu/format/)); a
  file starting with a UTF-8 byte order mark is read normally.

Artist and title are compared case-insensitively with collapsed whitespace.
A duet arrangement is never grouped with a solo one - that's an intentional
variant. **Dismiss** remembers a group by its artist/title/duet key, so it
stays dismissed after files change (until the tags themselves change).
Dismissing in one section never affects the other.

Scanning every song file is expensive, so results are cached. **Rescan**
refreshes them on demand, and they refresh automatically once a month
(`DUPLICATES_RESCAN_DAY`/`_HOUR`/`_MINUTE`, see
[deploy.md](deploy.md#configuration)).

## Integrity

Three checks, computed on every view (**Rescan** forces a fresh look):

**Song file format** (`app/format_check.py`). Every `.txt` file is checked
against the [UltraStar format spec](https://github.com/UltraStar-Deluxe/format):
missing mandatory tags, broken media references, malformed numbers,
unparsable lines, a UTF-8 byte order mark at the start (a warning - the
spec wants UTF-8 without one; the dashboard itself reads such files
normally). An **error** breaks playback, a **warning** is a spec
deviation that doesn't. A missing or empty `#VIDEO` tag is an error
("Missing #VIDEO"); when a video file (`.mp4`, `.mkv`, `.avi`, `.webm`,
`.mpg`, `.mpeg`, `.m4v`, `.mov`, `.flv`, `.divx`, `.wmv`) sits in the song's
folder, the file also gets "Video file not referenced", naming the videos
the tag could point at. A file whose only issue is a missing `#VERSION` tag
is left out, since that's true of most older libraries. The page shows the
number of affected files and filters by issue type (e.g. only "#VIDEO file
not found").

This list exports as an UltraStar playlist (`.upl`, matched by artist and
title). Open it in
[UltraStar Manager](https://github.com/UltraStar-Deluxe/UltraStar-Manager)
to jump straight to those songs. UltraStar Manager is vendored read-only at
`third_party/ultrastar-manager` as a git submodule, only as the reference for
the `.upl` format (`src/playlist/QUPlaylistFile.cpp`); run
`git submodule update --init` to fetch it.

**Folder structure** (`app/structure_check.py`). The library convention is
flat `Artist - Title` folders. A folder may hold several songs, but a nested
subfolder or a name without the separator is flagged, with a file tree that
shows why. A `@eaDir` subfolder (Synology's thumbnail cache) and a subfolder
named `-` (the set-aside folder) are not flagged.

**Misplaced songs** (`app/misplaced_check.py`). A song whose own
`#ARTIST`/`#TITLE` tags don't match the folder it's in - for example an
unrelated song dumped into a correctly named folder by a batch import. The
comparison ignores `()`/`[]` asides (a yt-dlp video ID, "(Official Audio)"),
a known label suffix like "Napalm Records", and treats filename-unsafe
characters such as `:` and `/` as interchangeable with the `-` or `|` that
replace them in names.

The structure and misplaced checks export a **move list** instead of a
playlist (`app/move_export.py`), since UltraStar Manager can't move files.
Apply it with `scripts/apply_moves.sh` - see
[library-scripts.md](library-scripts.md#apply-a-move-list).

## Users

Create users, reset passwords, grant or revoke contributor and admin,
disable and delete accounts. The Role column names the highest level: admin,
contributor or user (an admin's contributor flag doesn't matter, so admins
get no contributor button). A contributor may use Reported, Requested,
Duplicates and the genre [Edit](#edit) tab, but not Integrity, Users or
Settings. There's no self-registration; the first admin is created from
`ADMIN_USERNAME`/`ADMIN_PASSWORD` on first start.

## Settings

- **Form profiles** - the Request song and Report broken forms each switch
  independently between **karaoke night** (only the essentials required,
  quick to fill in during a party) and **strict** (everything the song
  pipeline needs). See the required fields under
  [Report broken](#report-broken) and [Request song](#request-song).
- **App mode** - **production** or **debug**. Debug raises the log level and
  lets an admin admit a request for a song that's already in the library.
- **Enable logging** - silences all logging when off, independent of mode.
- **Reported broken badge** (`app/broken_badge.py`) - how long the badge on
  the Songs and What's new pages shows. **Until the report is resolved**
  (the default): an admin resolves the report to remove it. **Until the song
  is updated or the report resolved**: it also goes away once the library
  scan read a write to the song's `.txt`, `.mp3` or `.opus` files newer than
  the report - a fix before the scan's first run included (the same check as
  the admin
  [Updated since report](#reported-and-requested) mark). With several open
  reports, it stays while one of them is newer than the write. The admin
  report lists always show every open report.
- **What's new period** - how far back the two What's new lists reach: a
  whole number (1-999) of days, weeks or calendar months, 2 months by
  default (`app/recent_period.py`). The start is exact to the moment - "2
  weeks" on a Tuesday at 15:00 starts two Tuesdays ago at 15:00.
- **Genres on the map** - how many of the biggest genres get their own
  cluster on the [Genres](#genres) Map and their own circle and tile on its
  Connections tab, from 1 to 24 (12 by default); the others fold into
  "Other genres".
- **Library scan schedule** - when the scan behind the What's new page runs,
  as a standard cron expression: minute, hour, day of month, month, weekday
  (0 and 7 are Sunday, `mon`-`sun` work too), in the app's time zone (`TZ`).
  Default `0 11 * * *`, daily at 11:00; `0 */6 * * *` is every 6 hours. A new
  schedule takes effect when saved; an invalid one is refused. The scan also
  runs once at every app start.
- **Library scan** - **Scan now** runs the scan behind the What's new
  page's "Recently added"/"Recently updated" panels right away instead of waiting
  for its schedule. **Reset** (asks for confirmation) forgets every recorded
  date and scans as if for the first time: every current folder counts as
  old and both panels start empty.

The footer shows admins the running build's version (e.g. `v2026.10.11-42`).
