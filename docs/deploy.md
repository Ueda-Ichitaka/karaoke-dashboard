# Deployment

Karaoke Dashboard runs as a docker-compose stack of two containers: the app
and PostgreSQL 16. The steps follow the style of the
[mariushosting](https://mariushosting.com) Synology tutorials, but any
Docker host works the same way.

## Deploy on a Synology NAS

### 1. Folders

Via **File Station** create:

```
/volume1/docker/karaoke-dashboard
/volume1/docker/karaoke-dashboard/db
```

### 2. Environment file

Copy [`.env.example`](../.env.example) to `.env` inside
`/volume1/docker/karaoke-dashboard/` and fill it in. Generate the secrets:

```bash
openssl rand -hex 32   # SECRET_KEY
openssl rand -hex 24   # POSTGRES_PASSWORD
```

Set `ADMIN_PASSWORD` - the `admin` account is created automatically on first
start. Keep `SESSION_COOKIE_SECURE=true` unless you reach the app over plain
`http://`.

Values in `.env` must not be quoted and must not contain `$`, `#` or leading
or trailing spaces - compose would change them. Hex secrets avoid all of
that.

### 3. Compose file

Use [`docker-compose.yml`](../docker-compose.yml) and edit one line, the path
to your karaoke library (mounted read-only):

```yaml
    volumes:
      - /volume1/music/karaoke:/songs:ro
```

### 4. Start

Both containers restart unless you stop them (`restart: unless-stopped`).
Their healthchecks are defined but disabled, and the app container starts
as soon as the database container has started - the app itself retries the
database connection for about a minute until Postgres accepts it.

**Container Manager -> Project -> Create**, point it at the folder with
`docker-compose.yml` and `.env`, and start it. The image is pulled from
`ghcr.io/ueda-ichitaka/karaoke-dashboard:latest`.

### 5. Reverse proxy

Set up the Synology reverse proxy (**Control Panel -> Login Portal ->
Advanced -> Reverse Proxy**) from your chosen hostname to `127.0.0.1:9713`
(or your `WEB_PORT`), and log in through that hostname. Keep
`SESSION_COOKIE_SECURE=true` once the proxy terminates HTTPS.

`http://<NAS-IP>:9713` doesn't work directly, on purpose: the web port is
bound to `127.0.0.1`, so it's reachable from the NAS itself (where the
reverse proxy runs) but not from your LAN or the internet. Docker routes
every connection to a published port through the same bridge gateway
address, whatever its real origin, so the app can't tell a reverse proxy's
traffic from anyone else who reaches the port. Trusting `X-Forwarded-For` is
only safe when the proxy is the only way in. That's also what lets the login
lockout see each visitor's real IP (see [security.md](security.md)).

If you deliberately want direct LAN access without a proxy, drop the
`127.0.0.1:` prefix:

```yaml
    ports:
      - ${WEB_PORT:-9713}:8000
```

The address(es) the app trusts to set `X-Forwarded-For` default to
`127.0.0.1,172.16.0.0/12`; override them with `FORWARDED_ALLOW_IPS` in
`docker-compose.yml` if your proxy connects from elsewhere.

## Updating

```bash
docker compose pull && docker compose up -d
```

The database schema is created and updated automatically on startup: new
tables are created, new columns added and lengthened text columns widened.
There are no manual migration steps.

Browsers check `/static` files (styles and scripts) for changes on every page
load (`Cache-Control: no-cache`), so the new look shows right after an
update. A browser that saved `style.css` under an image from before this
setting may still show the old styling once - reload with Ctrl+Shift+R.

## Running a specific version

Every build gets a date-based version tag, `YYYY.MM.DD-<run number>` (e.g.
`2026.10.11-42`). To run an older build, pick one from the
[package page](https://github.com/Ueda-Ichitaka/karaoke-dashboard/pkgs/container/karaoke-dashboard)
("View and manage all versions") and replace `latest` in
`docker-compose.yml` with it:

```yaml
    image: ghcr.io/ueda-ichitaka/karaoke-dashboard:2026.10.11-42
```

The 10 newest builds are kept (see
[development.md](development.md#how-images-are-published)). The running
version is shown to admins in the page footer.

## Troubleshooting

Container logging is switched off in `docker-compose.yml` (`logging:
driver: none` on both containers), so the container log in Container
Manager stays empty. To see what the app does, remove the two `logging:`
lines from the `karaoke-dashboard` service, redeploy, and open its log. On
startup it prints:

```
[startup] connecting to database at karaoke-db:5432/karaoke
[startup] database connection OK
```

Put the lines back afterwards.

**`database unreachable ... after 30 attempts` / `Name or service not
known`** - the app can't reach the database. Check, in order:

1. Both containers were started from the **same** compose project, so they
   share one network. Deploying them separately doesn't work.
2. `POSTGRES_PASSWORD` in `.env` has no `$`, no `#`, no quotes and no stray
   spaces. Regenerate it with `openssl rand -hex 24` if unsure.
3. If you changed `POSTGRES_PASSWORD` after the first start, the database
   volume still holds the **old** password. Remove the stack, delete the
   contents of `/volume1/docker/karaoke-dashboard/db`, and start again. This
   deletes all reports, requests and users.

**`password authentication failed for user "karaoke"`** - same as (3): the
volume was initialised with a different password.

## Configuration

All settings are environment variables (see `.env.example` and
`app/config.py`).

| Variable | Default | Notes |
| --- | --- | --- |
| `POSTGRES_HOST` / `POSTGRES_PORT` | `db` / `5432` | Database host and port. The compose file sets the host to `karaoke-db`. |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | `karaoke` / `karaoke` / `karaoke` | The app URL-encodes the password, so `@ : / % #` in it are safe for the app (the `.env` rules above still apply). |
| `DATABASE_URL` | *(empty)* | Optional full SQLAlchemy URL that overrides the `POSTGRES_*` parts, e.g. `sqlite:///./dev.db`. |
| `SECRET_KEY` | *(insecure dev value)* | **Required in production.** Signs the session cookie. |
| `SESSION_COOKIE_SECURE` | `true` | Send the session cookie over HTTPS only. |
| `SONGS_DIR` | `/songs` | Directory scanned for song folders. Mount it read-only. |
| `SONG_SEPARATOR` | `" - "` | Splits `Artist - Title` folder names. |
| `SONG_IGNORE_NAMES` | `["@eaDir", "#recycle", "#snapshot", "lost+found"]` | Folder names in the library that are never songs (Synology system folders). A JSON list; setting it replaces the whole list. |
| `SCAN_CACHE_SECONDS` | `30` | How long the folder listing is cached before rescanning. |
| `PAGE_SIZE` | `60` | Songs per page. |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | `admin` / *(empty)* | First-run admin account. No admin is created while the password is empty. |
| `CSV_INCLUDE_HEADER` | `true` | Header row in the CSV exports. |
| `DUPLICATES_RESCAN_DAY` | `1` | Day of month (1-28) the duplicates report rescans automatically. |
| `DUPLICATES_RESCAN_HOUR` / `_MINUTE` | `3` / `0` | Time of that rescan, 24h, in `TZ`. |
| `LIBRARY_SCAN_ON_START` | `true` | Run the library scan behind the What's new page once at app start. Its schedule is set on the admin Settings page. |
| `TZ` | `Europe/Berlin` (compose) | Timezone for the timestamps shown in admin tables. |
| `WEB_PORT` | `9713` (compose) | Host port the app is published on. |
| `FORWARDED_ALLOW_IPS` | `127.0.0.1,172.16.0.0/12` | Addresses trusted to set `X-Forwarded-For`; read by the container's start command. |
| `APP_TITLE` | `Karaoke Dashboard` | Shown in the header and page titles. |
