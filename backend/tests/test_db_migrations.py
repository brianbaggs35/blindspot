"""The migrations: fresh install, up and down, running again, and the helpers they use."""

import runpy
import sys

import psycopg
import pytest
import sqlalchemy as sa
from alembic import command
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy.engine import Connection

from app.db.ensure import (
    drop_table_if_exists,
    ensure_column,
    ensure_index,
    ensure_table,
    ensure_unique_constraint,
)
from app.db.events import connection_string
from app.db.migrate import MIGRATION_LOCK_KEY, alembic_config, main, take_migration_lock, upgrade


def tables(url: str) -> set[str]:
    with psycopg.connect(connection_string(url)) as connection:
        rows = connection.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
        )
        return {row[0] for row in rows}


def test_a_fresh_database_gets_the_tables(database_url: str) -> None:
    upgrade(database_url)
    assert {"app_setting", "alembic_version"} <= tables(database_url)


def test_the_models_and_the_migrations_agree(database_url: str) -> None:
    upgrade(database_url)
    # Raises if a model has a change that no migration covers.
    command.check(alembic_config(database_url))


def test_up_down_and_up_again(database_url: str) -> None:
    config = alembic_config(database_url)
    upgrade(database_url)
    command.downgrade(config, "base")
    assert "app_setting" not in tables(database_url)
    upgrade(database_url)
    assert "app_setting" in tables(database_url)


def test_the_newest_migration_can_run_again_without_changing_anything(database_url: str) -> None:
    config = alembic_config(database_url)
    upgrade(database_url)
    with psycopg.connect(connection_string(database_url), autocommit=True) as connection:
        connection.execute("INSERT INTO app_setting (key, value) VALUES ('kept', 'true')")
    command.stamp(config, "base")  # as if it had not been recorded as applied
    upgrade(database_url)
    command.check(config)
    with psycopg.connect(connection_string(database_url)) as connection:
        assert connection.execute("SELECT key FROM app_setting").fetchall() == [("kept",)]


def test_main_upgrades_the_configured_database(database_url: str) -> None:
    assert main() == 0
    assert "app_setting" in tables(database_url)


def test_only_one_migration_runs_at_a_time(database_url: str) -> None:
    engine = sa.create_engine(database_url)
    with engine.connect() as first, engine.connect() as second:
        take_migration_lock(first)
        query = sa.text("SELECT pg_try_advisory_xact_lock(:key)")
        assert second.execute(query, {"key": MIGRATION_LOCK_KEY}).scalar() is False
        second.rollback()
        first.rollback()  # ends the transaction, which releases the lock
        assert second.execute(query, {"key": MIGRATION_LOCK_KEY}).scalar() is True
    engine.dispose()


@pytest.fixture
def operations(database_url: str):
    engine = sa.create_engine(database_url)
    with engine.begin() as connection, Operations.context(MigrationContext.configure(connection)):
        yield connection
    engine.dispose()


def names(connection: Connection, table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(connection).get_columns(table)}


def test_ensure_table_makes_the_table_once(operations: Connection) -> None:
    for _ in range(2):
        ensure_table("widget", sa.Column("id", sa.Integer, primary_key=True))
    assert names(operations, "widget") == {"id"}


def test_ensure_column_adds_the_column_once(operations: Connection) -> None:
    ensure_table("widget", sa.Column("id", sa.Integer, primary_key=True))
    for _ in range(2):
        ensure_column("widget", sa.Column("label", sa.String(20)))
    assert names(operations, "widget") == {"id", "label"}


def test_ensure_index_and_constraint_are_made_once(operations: Connection) -> None:
    ensure_table(
        "widget", sa.Column("id", sa.Integer, primary_key=True), sa.Column("label", sa.String(20))
    )
    for _ in range(2):
        ensure_index("ix_widget_label", "widget", ["label"])
        ensure_unique_constraint("uq_widget_label", "widget", ["label"])
    inspector = sa.inspect(operations)
    assert "ix_widget_label" in {index["name"] for index in inspector.get_indexes("widget")}
    constraints = inspector.get_unique_constraints("widget")
    assert [constraint["name"] for constraint in constraints] == ["uq_widget_label"]


def test_drop_table_if_exists_drops_once(operations: Connection) -> None:
    ensure_table("widget", sa.Column("id", sa.Integer, primary_key=True))
    for _ in range(2):
        drop_table_if_exists("widget")
    assert not sa.inspect(operations).has_table("widget")


def test_running_the_module_upgrades_and_exits_cleanly(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delitem(sys.modules, "app.db.migrate")  # run it afresh, as `python -m` does
    with pytest.raises(SystemExit) as stopped:
        runpy.run_module("app.db.migrate", run_name="__main__")
    assert stopped.value.code == 0
    assert "app_setting" in tables(database_url)
