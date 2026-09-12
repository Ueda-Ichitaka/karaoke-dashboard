# Backlog

Ideas and deferred work that came up during feature work but are out of
scope for the change that raised them.

## Adopt Alembic for schema migrations

**Raised:** 2026-09-12, while adding `language`/`musicbrainz_id`/`lyrics_url`
to `SongRequest`. `app/database.py: init_db()` only calls
`Base.metadata.create_all()`, which creates missing tables but never alters
existing ones - schema changes currently ship as a small idempotent
`ALTER TABLE ... ADD COLUMN IF NOT EXISTS` helper alongside it (see
`app/database.py: _sync_schema()` or equivalent). That doesn't scale to
renames, data backfills, or column drops.

**Proposal:** introduce Alembic, generate a versioned migration for the
columns added in this change (and any added since), and run
`alembic upgrade head` as a startup/deploy step in place of (or alongside)
`create_all()`.
