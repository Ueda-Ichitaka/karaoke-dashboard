# 🎤 Karaoke Dashboard

A small web app for a home karaoke system:

| Tab | Who | What |
| --- | --- | --- |
| **Songs** | everyone | Browse & search the library (one entry per folder in your songs directory). |
| **Report broken** | logged-in users | Pick a song, describe what's broken, submit. |
| **Request song** | logged-in users | Ask for a new song: band + title (required), YouTube link (optional). |
| **Reported** | admins | Review / resolve broken-song reports. |
| **Requested** | admins | Review / close song requests, **export as CSV**. |
| **Duplicates** | admins | Review songs that appear more than once, compare their metadata, dismiss false positives. |
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
on future scans, even after the underlying files change.

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

Use [`docker-compose.yml`](docker-compose.yml). **Edit two lines** for your NAS:

```yaml
    volumes:
      - /volume1/music/karaoke:/songs:ro   # <-- your real karaoke library path
```

```yaml
    ports:
      - 9713:8000                          # <-- host port you want (or set WEB_PORT in .env)
```

### 4. Start

**Container Manager → Project → Create**, point it at the folder with
`docker-compose.yml` and `.env`, and start it. The image is pulled from
`ghcr.io/ueda-ichitaka/karaoke-dashboard:latest`.

Open `http://<NAS-IP>:9713` and log in as `admin`. For public access, put it
behind the Synology **reverse proxy** (adds HTTPS) and keep
`SESSION_COOKIE_SECURE=true`.

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
| `CSV_INCLUDE_HEADER` | `true` | Header row in the requested-songs CSV export. |
| `APP_TITLE` | `Karaoke Dashboard` | Shown in the header and page titles. |

Synology system folders (`@eaDir`, `#recycle`, …) and dot-folders are ignored
when scanning.

### CSV export

`Requested` tab → **Export open CSV** / **Export all CSV**. Columns:
`band name, song name, youtube link`, comma-separated, `\n` row terminator,
UTF-8. Header row unless `CSV_INCLUDE_HEADER=false`.

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
delete untagged package versions and keep only the 10 newest tagged ones, so
the package page doesn't accumulate clutter from old builds.

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
  duplicates.py      cross-folder duplicate-song detection + dismissal
  deps.py            current-user / auth guards / template helper
  routes/            songs, auth, reports, requests, admin
  templates/         Jinja2 templates
  static/            style.css, app.js (progressive enhancement)
tests/               pytest end-to-end tests
```
