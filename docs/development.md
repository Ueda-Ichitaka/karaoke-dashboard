# Development

Built with FastAPI, Jinja2 and SQLAlchemy 2, server-rendered, with a little
vanilla JavaScript as progressive enhancement. PostgreSQL in production,
SQLite works for local runs and tests.

## Run locally

Create a few song folders so the list has content (`songs-sample/` is
git-ignored):

```bash
mkdir -p "songs-sample/Queen - Bohemian Rhapsody" "songs-sample/a-ha - Take On Me"
```

**App only, on your machine:**

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
export SECRET_KEY=dev SESSION_COOKIE_SECURE=false \
       DATABASE_URL="sqlite:///./dev.db" \
       SONGS_DIR="$PWD/songs-sample" \
       ADMIN_USERNAME=admin ADMIN_PASSWORD=adminadmin
uvicorn app.main:app --reload
```

**Full stack in Docker** (PostgreSQL + app with hot reload): first point the
songs bind-mount in `docker-compose.dev.yml` at your library or at
`./songs-sample`, then:

```bash
docker compose -f docker-compose.dev.yml up --build
```

Either way, open <http://localhost:8000> and log in as `admin` /
`adminadmin`.

## Tests and lint

```bash
pytest
ruff check .
```

The test suite builds its own throwaway song directory and SQLite database,
so it needs nothing in `songs-sample/`.

## How images are published

`.github/workflows/docker-publish.yml` runs on every push to `main`:

1. lint and tests;
2. build a multi-arch image (`linux/amd64`, `linux/arm64`). Provenance/SBOM
   attestations are off: they add extra manifest entries per platform that
   Portainer and older Docker clients don't filter out, so a `:latest` pull
   would fetch 4 "images" instead of 2;
3. push to `ghcr.io/<owner>/<repo>`, tagged `latest`, `main`, `sha-<short>`,
   the date-based version `YYYY.MM.DD-<run number>` (UTC build date plus the
   workflow's run number, e.g. `2026.10.11-42` - unique and sortable), and on
   a `v*.*.*` git tag the semver.

The date-based version is also the image's `org.opencontainers.image.version`
label (unless a semver tag outranks it) and is baked into the image as
`APP_VERSION` (`app/__init__.py`), shown to admins in the page footer. Outside
the image it shows `vdev`.

The workflow uses the repo's built-in `GITHUB_TOKEN`; no secrets to
configure. Make the GHCR package public, or log the NAS in with a personal
access token, so Container Manager can pull.

`.github/workflows/ghcr-cleanup.yml` runs weekly (and on manual dispatch). It
keeps the 10 newest tagged builds and deletes the per-platform manifests
nothing references any more. A kept build's manifests are never touched -
deleting them would break that image.

## Database schema

`app/database.py: init_db()` runs on every start: it creates missing tables,
adds missing nullable columns to existing tables, and on PostgreSQL widens
text columns the model has made longer. It never touches rows. Renames,
backfills and drops would need real migrations - see
[BACKLOG.md](../BACKLOG.md) for adopting Alembic.

## Project layout

```
app/
  main.py               FastAPI app, middleware, error handlers
  config.py             settings from environment variables
  database.py           engine, session, wait-for-db, schema creation and sync
  models.py             database tables
  security.py           password hashing, admin seed
  deps.py               current user, auth guards (user, contributor, admin), template rendering
  csrf.py               CSRF tokens
  rate_limit.py         login lockout
  scheduler.py          background jobs: duplicates rescan, library scan
  app_settings.py       the admin settings row (profiles, mode, logging, badge, scan, period, map)
  app_mode.py           production/debug mode choices
  app_logging.py        log level, tied to the app mode
  profiles.py           karaoke-night/strict required fields for both forms and the admit check

  songs.py              folder scan and cached search index
  ultrastar.py          UltraStar .txt metadata parsing (cover, length, duet, ...)
  known_broken.py       songs with a pending or open report, for the badge
  library_history.py    library scan for the "Recently added"/"Recently updated" panels
  recent_period.py      the What's new period (amount and unit)
  broken_badge.py       how long the "Reported broken" badge stays
  static_files.py       /static with Cache-Control: no-cache
  song_genres.py        genres read from the song files, genre edits and their export
  genre_layout.py       the Genres Map and Connections drawings as SVG coordinates

  validation.py         shared form field validation
  languages.py          language choices (ISO 639-1 + "Mixed")
  broken_categories.py  report categories
  genres.py             review-only genre choices for requests and reports
  traits.py             review-only vocal/instrument trait choices
  duet.py               yes/no duet choice
  musicbrainz.py        bare MBID from a pasted musicbrainz.org URL
  request_matching.py   does a request already exist (library, pending, admitted)?
  report_matching.py    finds and merges a duplicate report
  import_merge.py       CSV reading and merge rules shared by both imports
  report_import.py      broken.csv import
  request_import.py     song-requests.csv import

  duplicates.py         duplicate-song detection, caching, dismissal
  format_check.py       UltraStar format checks
  structure_check.py    "Artist - Title" folder structure checks
  misplaced_check.py    wrong-song-in-folder checks
  upl_export.py         UltraStar playlist (.upl) export
  move_export.py        move-list export for scripts/apply_moves.sh

  routes/               songs, auth, reports, requests, admin
  templates/            Jinja2 templates
  static/               style.css, app.js, checkbox-groups.js
scripts/                standalone library tools, not in the image (see library-scripts.md)
tests/                  pytest tests
docs/                   this documentation; screenshots in docs/screenshots/, workflow diagrams in docs/workflows/
third_party/            UltraStar Manager as a read-only reference (git submodule)
```
