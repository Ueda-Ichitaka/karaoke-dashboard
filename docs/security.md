# Security

## Login

Passwords are hashed with bcrypt (`app/security.py`). On top of that, in
`app/routes/auth.py`:

- **Timing-safe verification** (`security.verify_login`). A login for an
  unknown or disabled user still runs a real bcrypt comparison against a
  fixed dummy hash, so "no such user" and "wrong password" take the same
  time and can't be told apart to enumerate usernames.
- **Brute-force lockout** (`app/rate_limit.py`). 5 failed attempts from one
  client IP within 5 minutes lock that IP out (429). It's keyed by IP, not
  username, so nobody can lock a real account out from elsewhere.
  - The count is kept in memory, which is correct for the single uvicorn
    process the app runs as (see `Dockerfile`, no `--workers`). Several
    workers or replicas would need a shared store such as Redis.
  - It only sees each visitor's real IP when the port is bound to
    `127.0.0.1` and reached through a reverse proxy (see
    [deploy.md](deploy.md#5-reverse-proxy)). Without that binding, anyone
    reaching the port directly could send a fresh `X-Forwarded-For` with
    every request and bypass the lockout.
- **Safe `next` parameter.** Only a same-site relative path is followed after
  login. A leading backslash is turned into a slash first, because browsers
  treat `/\evil.example.com` like `//evil.example.com`.
- **Oversized input refused early.** A username or password over a generous
  length limit is rejected before it reaches bcrypt or the database, also
  when an admin creates a user or resets a password.

## App-wide

- **CSRF protection** (`app/csrf.py`, `app/main.py`). Every rendered page gets
  a random per-session token (`app/deps.py: render()`), and every `POST` must
  send it back as a hidden `csrf_token` field. One middleware enforces it, so
  a new form or route is covered automatically; a missing or wrong token gets
  a 403 before the route runs. The token isn't rotated on login - see the
  docstring of `app/csrf.py` for why that's acceptable here.
- **Security headers** (`app/main.py`, on every response):
  `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`,
  `Referrer-Policy: same-origin`.
- **Request body limit** (`app/main.py: MAX_BODY_BYTES`, 256 KB). An
  oversized `POST` is rejected by its `Content-Length` before the body is
  read. Every field the app accepts is short text, so this is pure headroom.
- **SQL injection.** Every query goes through SQLAlchemy with bound
  parameters, never string interpolation.
- **Stored XSS.** Jinja2 autoescapes every `.html` template, so e.g. a
  `<script>` in a username is shown as text.

## CSV formula injection

Spreadsheet programs run a cell starting with `=`, `+`, `-` or `@` as a
formula. The exports guard against that:

- In `song-requests.csv`, a `band name`, `song name` or `musicbrainz_id`
  starting with one of those characters gets a leading `'`
  (`app/validation.py: neutralize_csv_formula`), so a request with band name
  `=cmd|'/c calc'!A0` can't run when opened in Excel or Sheets.
- In `broken.csv`, the free-text `description` is cleaned when it's
  submitted instead (see [csv.md](csv.md#brokencsv)).

## Tests

SQL injection and XSS are covered by `tests/test_login_security.py`, CSRF by
`tests/test_csrf.py`, the headers by `tests/test_security_headers.py` and the
body limit by `tests/test_body_size_limit.py`.
