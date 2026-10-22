# Features

Every page of Karaoke Dashboard in detail. For the CSV formats and imports
see [csv.md](csv.md); for the scripts that change files on disk see
[library-scripts.md](library-scripts.md).

| Tab | Who | What |
| --- | --- | --- |
| [Songs](#songs) | everyone | Browse and search the library |
| [What's new](#whats-new) | everyone | Songs recently added and recently updated |
| [Report broken](#report-broken) | logged-in users | Report a broken song |
| [Request song](#request-song) | logged-in users | Ask for a new song |
| [Reported](#reported-and-requested) | admins | Review, edit, resolve and export broken-song reports |
| [Requested](#reported-and-requested) | admins | Review, edit, close and export song requests |
| [Duplicates](#duplicates) | admins | Songs that exist more than once |
| [Integrity](#integrity) | admins | Format, folder structure and misplaced-song checks |
| [Users](#users) | admins | Accounts |
| [Settings](#settings) | admins | Form profiles, app mode, logging, badge mode, library scan |

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
run it, or reset it, from [Settings](#settings).

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

Both admin tabs work the same way.

**Needs review.** Newly submitted reports and requests aren't exportable
yet. Edit one to fill in anything missing, then **Admit** it into the
exportable list, or **Discard** it. The edit form's **Save and admit** button
saves first and then admits; if the admit check still finds something
missing, you stay on the form with the error shown.

**Genre and trait** (`app/genres.py`, `app/traits.py`) are admin-only tags,
never on the public forms. A song can have several genres (e.g. `metal`,
`gothic`) and several vocal/instrument traits (e.g. `harsh_vocals`, `choir`).
They default to "Default"/"None" and show in their own table columns.
Checking a trait unchecks "None", and checking "None" clears the traits.

**What admitting requires.** The admin Edit form and **Admit** use their own
fixed rules, independent of the public form's profile, so switching a
profile never changes what an admin must fill in:

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

**Updated since report.** An admitted report is marked **Updated since
report** in its *Song files* column when the library scan (see
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
  or media only), except the set-aside folder `-`.

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
unparsable lines. An **error** breaks playback, a **warning** is a spec
deviation that doesn't. A file whose only issue is a missing `#VERSION` tag
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

Create users, reset passwords, grant or revoke admin, disable and delete
accounts. There's no self-registration; the first admin is created from
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
