# 🎤 Karaoke Dashboard

A small web app for a home karaoke system:

| Tab | Who | What |
| --- | --- | --- |
| **Songs** | everyone | Browse & search the library (one entry per folder in your songs directory). |
| **Report broken** | logged-in users | Pick a song, choose a category (`#GAP`, out of sync, lyrics broken, missing video, missing audio, other), choose the song's language (required - includes a "Mixed" option for songs whose lyrics switch languages), describe what's broken (required only for "other"), give a genius.com lyrics link (required only for "lyrics broken" / "out of sync"), and optionally a cover image link, submit. |
| **Request song** | logged-in users | Ask for a new song: band + title (required); YouTube link, language (includes "Mixed"), MusicBrainz ID (bare ID or a pasted musicbrainz.org link - either is accepted), lyrics link, cover image link, Duet yes/no/blank - is a duet version wanted? (all optional). Rejected if the song already exists in the library *or* already has an open request. |
| **Reported** | admins | Review / resolve broken-song reports, **export as CSV** (`broken.csv`). |
| **Requested** | admins | Review / close / delete song requests, see whether one already matches the library, **export as CSV**. |
| **Duplicates** | admins | Review songs that appear more than once, compare their metadata, dismiss false positives. Results are cached (scanning is expensive) - rescan on demand or wait for the scheduled monthly rescan. |
| **Integrity** | admins | Song files checked against the UltraStar format spec, the library checked for the flat "Artist - Title" folder convention (nested/misnamed folders shown with a file tree), and misplaced songs (wrong song in an otherwise correctly-named folder) - all three exportable as an UltraStar Manager playlist. Rescan on demand with the button at the top. |
| **Users** | admins | Create users, reset passwords, grant/revoke admin, disable, delete. |

Built with **FastAPI + Jinja2 + SQLAlchemy**, server-rendered, no JS framework.
The song list is the set of sub-folders of a directory you mount into the
container (e.g. your existing karaoke library on the NAS). Reports, requests and
user accounts live in **PostgreSQL**.

Click a song row to expand it: every [UltraStar Deluxe](https://usdx.eu/) `.txt`
file in that folder (there can be more than one - batch-imported folders often
hold several distinct songs) is parsed into a metadata card - cover, length,
duet, genre, year, language. Length comes from the actual audio/video file the
song plays back (`#AUDIO`/`#MP3`/`#VIDEO`), not the rarely-present UltraStar
`#START`/`#END` tags. No JavaScript is involved; it's a native `<details>`
disclosure per row.

**Duplicates** (`app/duplicates.py`) groups every UltraStar entry in the
library by normalized artist + title, across folders *and* within a single
folder (e.g. two differently-named `.txt` charts for the same song sitting
next to each other). A group of two or more is a duplicate; its detail page
shows each copy's folder/filename and a field-by-field diff (genre, year,
language, length, cover, ...). A duet arrangement is never grouped with a
solo one - that's an intentional variant, not a duplicate. Reviewing a group
and clicking **Dismiss** records it (by its normalized key) so it's skipped
on future scans, even after the underlying files change. Scanning every
folder's UltraStar tags is expensive, so the group list is cached in memory
rather than recomputed on every page view - the **Rescan** button forces a
fresh scan, and it also happens automatically once a month (`DUPLICATES_RESCAN_DAY`
/ `_HOUR` / `_MINUTE`, see Configuration below).

**Integrity** (`app/format_check.py`, `app/structure_check.py`) runs two
independent checks, both computed live on every view (use the **Rescan**
button at the top to force a fresh look): every `.txt` file is checked
against the [UltraStar format spec](https://github.com/UltraStar-Deluxe/format)
(missing mandatory tags, broken media references, malformed numeric fields,
unparsable body lines - severities are **error** for things that break
playback and **warning** for spec deviations that don't; a file whose only
issue is a missing `#VERSION` tag is left out entirely - real but
non-breaking, and it would otherwise drown out genuine problems on an older
library); and every song folder is checked against the library's flat
`Artist - Title` convention - a folder may hold several songs, but a nested
subfolder or a name without the separator is flagged, with a file tree to
show why. A `@eaDir` subfolder (Synology's per-folder thumbnail cache) is
never treated as a nested subfolder for this check - it's NAS bookkeeping,
not a structure problem. Both kinds of non-conformance are typically
introduced by other library-management tools.
A third check flags **misplaced songs**: a song whose own `#ARTIST`/`#TITLE`
tags don't match the "Artist - Title" folder it's sitting in - e.g. a
batch-import bug that dumped an unrelated song's files into an otherwise
correctly-named folder - so it's clear which of several `.txt`s in a folder
actually belongs there. The comparison ignores `()`/`[]` asides (e.g. a
yt-dlp video ID or "(Official Audio)"), a known "Napalm Records"-style label
suffix, and treats filename-unsafe characters like `:` and `/` - and the `-`
or `|` that commonly replace them once they're part of a folder/file name -
as interchangeable, so those don't read as a mismatch. Any of the three
checks - format issues, non-conforming folders, or misplaced songs - can be
exported as an [UltraStar Deluxe playlist](https://usdx.eu/) (`.upl`,
matched by Artist + Title) scoped to just those songs - open it in
[UltraStar Manager](https://github.com/UltraStar-Deluxe/UltraStar-Manager)
to jump straight to them instead of browsing the whole library. That
project is vendored read-only at `third_party/ultrastar-manager` (a git
submodule, not built or run by this app) purely as a reference for its
`.upl` format (`src/playlist/QUPlaylistFile.cpp`); run
`git submodule update --init` after cloning if you want it locally.

---

## Deploy on a Synology NAS (Container Manager / docker-compose)

Style follows the [mariushosting](https://mariushosting.com) Synology tutorials.

### 1. Folders

Via **File Station** create:

```
/volume1/docker/karaoke-dashboard
/volume1/docker/karaoke-dashboard/db
```

### 2. Environment file

Copy [`.env.example`](.env.example) to `.env` inside
`/volume1/docker/karaoke-dashboard/` and fill it in. Generate the secrets:

```bash
openssl rand -hex 32   # SECRET_KEY
openssl rand -hex 24   # POSTGRES_PASSWORD
```

Set `ADMIN_PASSWORD` - the `admin` account is created automatically on first
start. `SESSION_COOKIE_SECURE=true` unless you reach the app over plain `http://`.

### 3. Compose file

Use [`docker-compose.yml`](docker-compose.yml). **Edit one line** for your NAS:

```yaml
    volumes:
      - /volume1/music/karaoke:/songs:ro   # <-- your real karaoke library path
```

The web port (`${WEB_PORT:-9713}`, set via `.env` if you want a different
one) is bound to `127.0.0.1` only - reachable from the NAS itself, not from
your LAN or the internet directly. This is deliberate: it forces every
visitor through a reverse proxy rather than the container's raw port,
closing an otherwise-real hole where trusting `X-Forwarded-For` from
"the Docker network" can't actually distinguish a real reverse proxy's
traffic from anyone who reaches the port directly - Docker NATs *every*
published-port connection through the same bridge gateway address,
regardless of true origin. Only change this if you deliberately want direct
LAN access without a proxy:

```yaml
    ports:
      - ${WEB_PORT:-9713}:8000              # <-- removes the 127.0.0.1 restriction
```

### 4. Start

**Container Manager → Project → Create**, point it at the folder with
`docker-compose.yml` and `.env`, and start it. The image is pulled from
`ghcr.io/ueda-ichitaka/karaoke-dashboard:latest`.

Set up the Synology **reverse proxy** (Control Panel → Login Portal →
Advanced → Reverse Proxy) pointing your chosen hostname at
`127.0.0.1:9713` (or your `WEB_PORT`), and log in through that hostname -
`http://<NAS-IP>:9713` no longer works directly, by design (see above). Keep
`SESSION_COOKIE_SECURE=true` once the proxy terminates HTTPS.

### Updating

```bash
docker compose pull && docker compose up -d
```

The database schema is created automatically; there are no manual migration
steps for now.

### Troubleshooting

The app prints what it's doing on startup:

```
[startup] connecting to database at karaoke-db:5432/karaoke
[startup] database connection OK
```

**`database unreachable ... after 30 attempts` / `Name or service not known`**
- the app can't resolve the DB host. Check, in order:

1. Both containers were started from the **same** compose project (so they share
   one network). Deploying the two containers separately will not work.
2. `POSTGRES_PASSWORD` in `.env` has no `$`, no `#`, no surrounding quotes and no
   stray spaces - compose mangles those and the value the DB gets won't match.
   Regenerate with `openssl rand -hex 24` if unsure.
3. If you changed `POSTGRES_PASSWORD` after the first start, the database volume
   still has the **old** password baked in. Wipe it and redeploy:
   remove the stack, delete the contents of
   `/volume1/docker/karaoke-dashboard/db`, start again.

**`password authentication failed for user "karaoke"`** - same as (3): the volume
was initialised with a different password. Wipe `…/db` and redeploy.

---

## Configuration

All settings are environment variables (see `.env.example` and `app/config.py`).

| Variable | Default | Notes |
| --- | --- | --- |
| `POSTGRES_HOST` / `POSTGRES_PORT` | `db` / `5432` | Database host/port. The compose file sets the host to `karaoke-db`. |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | `karaoke` / `karaoke` / `karaoke` | The app URL-encodes the password, so `@ : / % #` in it are safe. |
| `DATABASE_URL` | *(empty)* | Optional. A full SQLAlchemy URL that overrides the `POSTGRES_*` parts (e.g. `sqlite:///./dev.db` or a managed-DB URL). |
| `SECRET_KEY` | *(insecure dev value)* | **Required in production.** Signs the session cookie. |
| `SESSION_COOKIE_SECURE` | `true` | Send the session cookie only over HTTPS. |
| `SONGS_DIR` | `/songs` | Directory scanned for song sub-folders. Mount read-only. |
| `SONG_SEPARATOR` | `" - "` | Splits `Artist - Title` folder names. |
| `SCAN_CACHE_SECONDS` | `30` | How long the directory listing is cached before re-scanning. |
| `PAGE_SIZE` | `60` | Songs per page. |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | `admin` / *(empty)* | First-run admin seed. If the password is empty, no admin is created. |
| `CSV_INCLUDE_HEADER` | `true` | Header row in the requested-songs/broken-songs CSV exports. |
| `DUPLICATES_RESCAN_DAY` | `1` | Day of month (1-28) the duplicates report auto-rescans. |
| `DUPLICATES_RESCAN_HOUR` / `_MINUTE` | `3` / `0` | 24h time (in `TZ`) for that auto-rescan. |
| `APP_TITLE` | `Karaoke Dashboard` | Shown in the header and page titles. |

Synology system folders (`@eaDir`, `#recycle`, …) and dot-folders are ignored
when scanning.

### CSV export

`Requested` tab → **Export open CSV** / **Export all CSV**. Columns:
`band name, song name, youtube link, language, musicbrainz_id, lyrics_url, cover_url, duet`,
comma-separated, `\n` row terminator, UTF-8. Header row unless
`CSV_INCLUDE_HEADER=false`. The last five columns are optional/blank unless
the requester filled them in on the request form (`duet` is `yes`, `no` or blank; `cover_url` must be an http(s) link); they're consumed by the
UltraSinger batch pipeline (see `UPSTREAM_REQUESTS.md`) - `language` pins
whisper's language detection, `musicbrainz_id` enables a direct metadata
lookup instead of a fuzzy search, and `lyrics_url` is tried before an online
lyrics search (only a genius.com song page or a direct `.txt`/`.lrc` link
actually work; anything else - including a filesystem path an admin may set -
falls back silently, it's never an error). `musicbrainz_id` accepts either
the bare ID or a pasted `musicbrainz.org` URL - the ID is extracted from the
URL automatically (see `app/musicbrainz.py`), so the stored value always
fits the column and matches what the downstream lookup expects.

`Reported` tab → **Export open CSV** / **Export all CSV** (`broken.csv`).
Columns: `band, song name, category, description, lyrics_url, language, cover_url`,
same format as above. `category` is one of the fixed codes in
`app/broken_categories.py` (`gap`, `async`, `lyrics`, `video`, `audio`,
`other`) - `lyrics` and `async` also require a genius.com lyrics link on the
report form (stored as `BrokenReport.genius_url`, exported here as
`lyrics_url` to match the UltraSinger-side column name). `description` is
sanitized at submission time (`app/validation.py: sanitize_free_text`):
collapsed to a single line and stripped of characters that could break a CSV
row or trigger a spreadsheet formula (commas, semicolons, quotes, a leading
`=`/`+`/`-`/`@`, ...). Unlike the request form, `language` is **mandatory**
on the report form - a reporter of an "async"/"lyrics" report is usually
exactly the person who'd know the song's language.

---

## Security

Password hashing is bcrypt (`app/security.py`). A few login-specific
hardening measures on top of that, all in `app/routes/auth.py`:

- **Timing-safe verification** (`security.verify_login`): a login for a
  nonexistent/inactive user still runs a real bcrypt comparison (against a
  fixed dummy hash) instead of short-circuiting, so "no such user" and
  "wrong password" take the same time - otherwise the difference is a
  side-channel for enumerating valid usernames.
- **Brute-force lockout** (`app/rate_limit.py`): 5 failed attempts from the
  same client IP within 5 minutes locks out further attempts (429) from
  that IP, success or failure. Keyed by IP, not username, so an attacker
  can't use it to lock a real account out from elsewhere. **In-memory
  only** - correct for the single uvicorn process this app runs as today
  (see `Dockerfile` - no `--workers`); switching to multiple
  workers/replicas would need a shared store (e.g. Redis) instead, since
  each process would track its own count. **Also depends on the port
  binding**: this only sees a real per-visitor IP (rather than every
  request colliding on one shared bucket) when `docker-compose.yml`'s port
  is bound to `127.0.0.1` and reached only through a reverse proxy - see
  the deploy section above for why (Docker NATs any published-port
  connection through the same bridge gateway address regardless of its
  true origin, so trusting `X-Forwarded-For` without that binding lets an
  attacker who reaches the port directly spoof a fresh IP on every
  request and bypass the lockout entirely).
- **Open-redirect-proof `next` parameter**: only a same-site relative path
  is honored; a leading backslash is normalized to a forward slash first,
  since browsers treat `\` the same as `/` when resolving a URL and
  `/\evil.example.com` would otherwise slip past a naive scheme/netloc
  check and resolve as `//evil.example.com`.
- **Oversized input rejected early**: username/password over a generous
  length ceiling are refused before reaching bcrypt or the database
  (also enforced on admin user creation/password reset).
- **Security headers** (`app/main.py`, applied to every response):
  `X-Frame-Options: DENY` (clickjacking), `X-Content-Type-Options: nosniff`,
  `Referrer-Policy: same-origin`.

**CSRF protection** (`app/csrf.py`, `app/main.py`) applies app-wide, not
just to login: a random per-session token (synchronizer-token pattern) is
handed to every rendered page (`app/deps.py: render()`) and must come back
as a hidden `csrf_token` field on every `POST` - enforced centrally by one
middleware rather than per-route, so a new form/route is covered
automatically. A request missing or mismatching it gets a 403 before the
route ever runs. Not rotated on login - see `app/csrf.py`'s docstring for
why that's an acceptable trade-off here.

SQL injection isn't possible - every query goes through SQLAlchemy's ORM
with bound parameters, never raw string interpolation - and stored XSS
(e.g. a `<script>` in a username) is neutralized by Jinja2's autoescaping,
on by default for `.html` templates. Both are covered by regression tests
in `tests/test_login_security.py`; CSRF has its own suite in
`tests/test_csrf.py`.

A couple more, app-wide:

- **Request body size cap** (`app/main.py: MAX_BODY_BYTES`, 256 KB): an
  oversized `POST` is rejected on `Content-Length` before its body is ever
  read into memory - every field this app accepts is short text, so this
  is pure headroom, not a real limit.
- **CSV formula injection** (`app/validation.py: neutralize_csv_formula`):
  a `band name`/`song name`/`musicbrainz_id` starting with `=`, `+`, `-` or
  `@` is prefixed with `'` in the `song-requests.csv` export, so a
  malicious request (e.g. band name `=cmd|'/c calc'!A0`) can't execute as a
  formula when the admin opens the file in Excel/Sheets. `broken.csv`'s
  `description` field is protected differently (see the CSV export section
  above) since it's free text, not an identity field worth preserving
  byte-for-byte.

---

## Local development

```bash
# Put a few folders in ./songs-sample so the list has content (git-ignored):
mkdir -p "songs-sample/Queen - Bohemian Rhapsody" "songs-sample/a-ha - Take On Me"

# Option A - full stack in Docker (Postgres + app, hot reload)
docker compose -f docker-compose.dev.yml up --build
# -> http://localhost:8000   login: admin / adminadmin

# Option B - app only, on your machine
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
export SECRET_KEY=dev SESSION_COOKIE_SECURE=false \
       DATABASE_URL="sqlite:///./dev.db" \
       SONGS_DIR="$PWD/songs-sample" \
       ADMIN_USERNAME=admin ADMIN_PASSWORD=adminadmin
uvicorn app.main:app --reload
```

Tests and lint:

```bash
pytest
ruff check .
```

`songs-sample/` is git-ignored - create it locally with a few folders (or point
`SONGS_DIR` at your real library). The test suite builds its own throwaway
song directory, so it needs nothing there.

---

## How images are published

`.github/workflows/docker-publish.yml` runs on every push to `main`:

1. lint + tests,
2. build a multi-arch image (`linux/amd64`, `linux/arm64`) with provenance/SBOM
   attestations turned off (they add extra manifest entries per platform that
   Portainer and older Docker clients don't filter out, so a single `:latest`
   pull would fetch 4 "images" instead of 2),
3. push to `ghcr.io/<owner>/<repo>` tagged `latest`, `sha-<short>`, and - on a
   `v*.*.*` git tag - the semver.

No secrets to configure; it uses the repo's built-in `GITHUB_TOKEN`. Make the
GHCR package public (or log the NAS in with a PAT) so Container Manager can pull.

`.github/workflows/ghcr-cleanup.yml` runs weekly (and on manual dispatch) to
keep only the 3 newest tagged builds and delete their now-unreferenced
per-platform manifests, so the package page doesn't accumulate clutter from
old builds. A tagged build's own manifests are only eligible for deletion
once that tag itself falls out of the kept set - a still-kept tag's manifests
are never touched, since deleting them would break that image.

---

## Project layout

```
app/
  main.py            FastAPI app, middleware, error handlers
  config.py          env-based settings
  database.py        engine, session, wait-for-db, create tables
  models.py          User, BrokenReport, SongRequest, DismissedDuplicate
  security.py        password hashing, admin seed
  songs.py           filesystem scan + cached search index
  ultrastar.py       UltraStar .txt metadata parsing (cover, length, duet, ...)
  duplicates.py      cross-folder duplicate-song detection, caching + dismissal
  scheduler.py        monthly auto-rescan of the duplicates cache
  format_check.py    UltraStar format-spec conformity checks
  structure_check.py flat "Artist - Title" library structure checks
  misplaced_check.py wrong-song-in-folder checks
  upl_export.py      UltraStar Manager (.upl) playlist export for both checks above
  request_matching.py  does a song request already exist in the library or the request queue?
  duet.py            yes/no/blank Duet choice for the request form
  languages.py       language choices shared by the request/report forms (ISO 639-1 + "Mixed")
  broken_categories.py  fixed category list for the broken-report form
  musicbrainz.py     extracts a bare MBID from a pasted musicbrainz.org URL
  validation.py      shared request-form / broken-report field validation
  deps.py            current-user / auth guards / template helper
  routes/            songs, auth, reports, requests, admin
  templates/         Jinja2 templates
  static/            style.css, app.js (progressive enhancement)
tests/               pytest end-to-end tests
```
