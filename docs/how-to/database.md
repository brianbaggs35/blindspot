# The database

Blindspot keeps everything in one PostgreSQL 18 database. The app reaches it through
SQLAlchemy 2 (async) and psycopg 3. Changes to its structure are Alembic migrations.

## Where it listens

In the container the server has no network port. The API connects over the unix socket in
`/run/postgresql` as the `blindspot` role, and the server trusts the operating system user
(peer authentication), so there is no database password anywhere. The default
`BLINDSPOT_DATABASE_URL` is:

```
postgresql+psycopg://blindspot@/blindspot?host=/run/postgresql
```

For development, point `BLINDSPOT_DATABASE_URL` at any PostgreSQL 18 server.

## The pieces

| File                         | What it does                                                                                                       |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| `app/db/base.py`             | `Base` with a naming convention, and the shared columns: `UUIDPrimaryKey`, `Timestamps`, `SoftDelete`, `CreatedBy` |
| `app/db/models.py`           | The tables                                                                                                         |
| `app/db/session.py`          | `Database` (the pool) and `SessionDep`, one session per request: committed on success, rolled back on error        |
| `app/db/events.py`           | `notify` and `listen`: live events between the worker and the API with PostgreSQL's `LISTEN` and `NOTIFY`          |
| `app/db/ensure.py`           | `ensure_table`, `ensure_column`, `ensure_index`, `ensure_unique_constraint`, `drop_table_if_exists`                |
| `app/db/migrate.py`          | `python -m app.db.migrate` upgrades to the newest revision, holding an advisory lock so only one process migrates  |
| `migrations/`, `alembic.ini` | The migrations                                                                                                     |

Ids are UUIDv7: random, but they sort by creation time. Times are stored in UTC and always have
a time zone. A deleted row (`SoftDelete`) is hidden with `deleted_at`; filter with
`Model.not_deleted()`.

Health and readiness: `GET /api/health` answers while the server runs. `GET /api/ready` also
needs the database to answer, and gives a 503 problem document (`database_unavailable`)
otherwise.

## Adding a table or a column

1. Change or add the model in `app/db/models.py`.
2. Make a migration: `cd backend && alembic revision --autogenerate -m "what changed"`, then read
   it. Replace `op.create_table`, `op.add_column` and `op.create_index` with the `ensure_*`
   helpers so that running the migration twice changes nothing. Name constraints in the migration
   as the naming convention would (`pk_table`, `uq_table_column`, `fk_table_column_other`).
3. Every new column needs a migration. A model change alone does nothing to a database that
   already exists.
4. Never edit a migration that has shipped. Fix forward with a new one.
5. Expand, then contract: add the new structure first and drop the old one in a later release.

CI runs this on PostgreSQL 18 and fails the pull request if any step fails:

```
alembic upgrade head
alembic check                  # the models and the migrations agree
alembic downgrade base
alembic upgrade head
alembic stamp <parent of head> # the newest migration runs again on a database that has it
alembic upgrade head
alembic check
```

## Tests

`BLINDSPOT_TEST_DATABASE_URL` names a PostgreSQL server the tests may use (for example
`postgresql+psycopg://blindspot@127.0.0.1:5432/blindspot`). Each test that needs a database
makes its own, with a random name, and drops it afterwards, so no two tests and no two runs share
one. The role needs the right to create databases.
