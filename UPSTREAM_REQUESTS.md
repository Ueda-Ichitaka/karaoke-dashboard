# Requests from UltraSinger (upstream consumer)

This file tracks requests from `/home/ueda/workspace/UltraSinger/stack/`
(the batch-processing "song factory" that consumes this project's CSV
export as its input list) for changes on this side. It reads
`requests.csv` (`GET /admin/requests.csv`) as its `songs.csv` input.

## Optional CSV export columns: language, musicbrainz_id, lyrics_url

**Status: implemented 2026-09-12** - `requests.csv` now exports all three
columns, and the request form has matching optional fields (a language
dropdown, plus MusicBrainz ID / lyrics link fields with hover tooltips).

**Requested:** 2026-09-11. **Update 2026-09-11:** all three columns are now
actively consumed on the UltraSinger side (previously only `language` was;
`musicbrainz_id`/`lyrics_url` were parsed-but-ignored placeholders) - their
exact behavior is now final, described below.

**Current export** (`app/routes/admin.py`, `requests_csv()`): three
columns, `band name, song name, youtube link`, sourced from `SongRequest`
(`app/models.py`) which only has `band_name`, `song_name`, `youtube_url`.

**Ask:** three additional *optional* columns, appended after the existing
three so the format stays backward compatible:

```csv
band name,song name,youtube link,language,musicbrainz_id,lyrics_url
Lacrimosa,Lichtgestalt,https://www.youtube.com/watch?v=XYZ,de,,
```

- **`language`** - ISO 639-1 code (e.g. `de`, `en`). Pins whisper's
  language detection instead of letting it auto-detect, which has
  mis-fired on short/ambiguous audio (a purely German song was once
  detected as English at 0.41 confidence and processed with the wrong
  language throughout the pipeline). If a requester already knows the
  song's language, passing it through avoids that class of bug entirely.
- **`musicbrainz_id`** - a MusicBrainz ID, if the requester happens to
  know one. **Either a recording ID or a release ID works** - UltraSinger
  auto-detects which kind it is (tries it as a recording first, falls
  back to release), so this project does not need to know or ask which
  type the requester is pasting. When resolvable, it replaces UltraSinger's
  fuzzy title/artist search with a direct lookup, giving more reliable
  cover art/year/genre metadata. **Does not affect the song's name** -
  `band name`/`song name` above always win regardless. An invalid/unknown
  ID is not an error - it's silently ignored and UltraSinger falls back to
  its normal fuzzy search, so this field never needs validation on this
  side.
- **`lyrics_url`** - a URL to known-good lyrics for the song, tried before
  UltraSinger's own online lyrics search and used directly if it works.
  **Only two kinds of link actually work:**
  1. A **genius.com song page URL** (e.g.
     `https://genius.com/Artist-song-title-lyrics`) - scraped directly.
  2. A URL pointing **straight at plain text or an `.lrc` file** (e.g. a
     raw pastebin/gist link, a `.txt`/`.lrc` file host) - fetched and used
     as-is.

  **Any other lyrics site's page URL (AZLyrics, Musixmatch, a lyrics
  wiki, ...) will NOT work** - UltraSinger does not scrape arbitrary HTML
  pages (a prior attempt at a similar integration - darklyrics.com - broke
  when that site changed its page structure, so this was a deliberate
  scope decision, not an oversight). If this project ever adds a form
  field/validation for `lyrics_url`, it would be worth restricting or at
  least hinting at "genius.com link, or a direct link to a .txt/.lrc file"
  rather than accepting any lyrics-site URL. A bad/unusable `lyrics_url`
  is not an error either - UltraSinger falls back to its normal online
  lyrics search.

All three should be optional/nullable - existing rows and any manually
maintained CSV without these columns must keep working unchanged.

**Why this matters now that the columns are consumed:** this project's
README already shows it parses "genre, year, language" out of existing
UltraStar `.txt` files for the library browse view, so a `language`
field/pattern may already exist somewhere in this codebase (a
select/dropdown, a validated ISO-code field) that could be reused for a
request-form field rather than building one from scratch.

**Not requested:** any UI/form changes are up to this project's own
judgment - the ask here is only about the CSV export shape and, now that
the fields are live, making sure whatever gets put in `lyrics_url` is one
of the two supported link kinds above. A same-page form field for
requesters to optionally supply these at request time would be the
obvious next step if that's wanted, but that's a decision for this
project, not a requirement from the UltraSinger side.

## Optional broken.csv column: lyrics_url

**Requested:** 2026-09-14. **Status: implemented 2026-09-14** - `broken.csv`
now exports a fifth `lyrics_url` column, sourced from a `genius_url` field
already captured on the report form (required there for the `lyrics`/
`async` categories, per this project's own validation - see
`app/broken_categories.py`). Named `lyrics_url` in the export to match this
ask exactly, even though the underlying model/form field is `genius_url`.

The UltraSinger side now reads `broken.csv` (`GET /admin/reports.csv`,
`app/routes/admin.py`'s `reports_csv()`) to repair only what a report's
`category` (see `app/broken_categories.py`) actually calls for, instead of
always running the same blind full repair - see that side's
`stack/README.md` ("Repairing with broken.csv"). For `category == "lyrics"`
specifically, a trusted lyrics link is tried before falling back to an
automatic online search - exactly the same `lyrics_url` mechanism
`song-requests.csv` already has (see above): only a genius.com song page,
or a URL pointing straight at plain text/`.lrc`, actually works.

**Ask:** one additional *optional* column, appended after the existing
four so the format stays backward compatible:

```csv
band,song name,category,description,lyrics_url
Metric,Black Sheep,lyrics,second verse is wrong,https://genius.com/Metric-black-sheep-lyrics
```

This would need a `lyrics_url` (or similar) field on `BrokenReport` (see
`app/models.py`) and its form/edit views, populated the same optional way
`SongRequest.lyrics_url` already is. The UltraSinger-side parser
(`broken_report.py`) already reads a `lyrics_url` column when present and
defaults to `""` when it's missing, so no further change is needed on that
side once this ships - existing exports without the column keep working
unchanged either way.

**Not requested:** any UI/form changes, same caveat as the `song-requests.csv`
ask above - this is only about the export shape.

## Optional broken.csv column: language

**Requested:** 2026-09-15. **Status: implemented 2026-09-18** - `broken.csv`
now exports a sixth `language` column, sourced from a `language` field on
`BrokenReport` (see `app/models.py`). Unlike `song-requests.csv`'s optional
`language` field, this one is **mandatory** on the report form (this
project's own choice, not requested upstream) - a reporter of an
"async"/"lyrics" report is usually exactly the person who'd know the song's
language, so it made sense to just always ask. The dropdown (shared with the
request form, see `app/languages.py`) also gained a "Mixed" option for songs
whose lyrics switch languages mid-track, absent before this.

The UltraSinger side is fixing a real, recurring sync-quality problem: a
repair sometimes re-aligns lyrics against the wrong detected language
(whisper's auto-detection can mis-fire, same class of bug as the
`Lichtgestalt` example under the `language` ask above). For a *new* song
request, `song-requests.csv`'s existing `language` column already lets a
requester pin this - there's no equivalent for a *broken-song report*,
even though a reporter reporting an "async"/"lyrics" category report is
often exactly the person who'd know the song's language.

**Ask:** one additional *optional* column, appended after the existing
`lyrics_url` column so the format stays backward compatible:

```csv
band,song name,category,description,lyrics_url,language
Lacrimosa,Lichtgestalt,async,drifts after the first line,,de
```

This would need a `language` field on `BrokenReport` (see `app/models.py`)
and its form/edit views, populated the same optional way
`SongRequest.language` already is (same ISO 639-1 code convention - a
language dropdown/select if this project already has one reusable from the
request form). The UltraSinger-side parser (`broken_report.py`) already
reads a `language` column when present and defaults to `""` when it's
missing, and threads it through to `repair.py --language`, so no further
stack-side change is needed once this ships - existing exports without the
column keep working unchanged either way.

**Note on precedence:** on the UltraSinger side, this value is only used
as a *fallback* - if the song's own folder already has a persisted,
possibly admin-edited `language.txt` (see that project's `src/modules/
language_file.py`), the saved file always wins over this column, the same
way a manually-supplied `lyrics.txt`/`lyrics_url` already takes priority
over an automatic fetch.

**Not requested:** any UI/form changes, same caveat as the asks above -
this is only about the export shape.
