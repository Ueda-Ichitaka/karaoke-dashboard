# Backlog

Ideas and deferred work that came up during feature work but are out of
scope for the change that raised them.

## Adopt Alembic for schema migrations

**Raised:** 2026-09-12, while adding `language`/`musicbrainz_id`/`lyrics_url`
to `SongRequest`. `app/database.py: init_db()` only calls
`Base.metadata.create_all()`, which creates missing tables but never alters
existing ones - schema changes currently ship as a small idempotent
`ALTER TABLE ... ADD COLUMN IF NOT EXISTS` helper alongside it (see
`app/database.py: _sync_schema()` or equivalent), which since 2026-10-16
also widens a text column whose model length was raised (a too-short
`trait` column broke admitting several traits on Postgres, while the
SQLite tests never noticed). That doesn't scale to renames, data
backfills, or column drops.

**Proposal:** introduce Alembic, generate a versioned migration for the
columns added in this change (and any added since), and run
`alembic upgrade head` as a startup/deploy step in place of (or alongside)
`create_all()`.

## Full logging instrumentation

**Raised:** 2026-10-03, while adding the admin Settings view's production/
debug mode (`app/app_mode.py`, `app/app_logging.py`). What shipped is a
minimal toggle: one app-wide Python logging level (INFO in production,
DEBUG in debug) plus a handful of `logger.info()` calls at the existing
notable points (startup, admit, discard).

**Proposal:** systematically add logger calls across every admin/report/
request route (every submit, admit, discard, edit, validation failure), so
debug mode visibly floods logs with per-action detail instead of just the
few points covered so far.
