"""The copy made before a migration, and the decision to make one."""

import stat
import time
from pathlib import Path

import psycopg
import pytest
from sqlalchemy.exc import OperationalError

from app.db import migrate
from app.db.backup import BackupError, back_up, pg_dump_arguments, prune
from app.db.events import connection_string

DUMPER = """#!/bin/sh
for argument in "$@"; do
  case "$argument" in --file=*) target="${argument#--file=}" ;; esac
done
echo "$@" > "$target"
"""
FAILING_DUMPER = """#!/bin/sh
echo "pg_dump: error: connection refused" >&2
echo partial > "$(echo "$@" | sed -n 's/.*--file=\\([^ ]*\\).*/\\1/p')"
exit 1
"""


def install_dumper(directory: Path, monkeypatch: pytest.MonkeyPatch, script: str) -> None:
    """Put a stand-in pg_dump first on PATH (the real one must match the server's version)."""
    program = directory / "pg_dump"
    program.write_text(script)
    program.chmod(program.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{directory}:/usr/bin:/bin")


def test_arguments_for_a_unix_socket() -> None:
    arguments = pg_dump_arguments(
        "postgresql+psycopg://blindspot@/blindspot?host=/run/postgresql", Path("/data/x.dump")
    )
    assert arguments == [
        "--format=custom",
        "--no-password",
        "--file=/data/x.dump",
        "--host=/run/postgresql",
        "--username=blindspot",
        "--dbname=blindspot",
    ]


def test_arguments_for_a_tcp_server() -> None:
    arguments = pg_dump_arguments(
        "postgresql+psycopg://me:secret@db.example:6543/app", Path("/x.dump")
    )
    assert "--host=db.example" in arguments
    assert "--port=6543" in arguments
    assert "--username=me" in arguments
    assert not any("secret" in argument for argument in arguments)  # never on the command line


def test_arguments_for_a_local_default() -> None:
    arguments = pg_dump_arguments("postgresql+psycopg:///app", Path("/x.dump"))
    assert arguments == ["--format=custom", "--no-password", "--file=/x.dump", "--dbname=app"]


def test_a_copy_is_named_for_the_revision_and_kept(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_dumper(tmp_path, monkeypatch, DUMPER)
    target = back_up("postgresql+psycopg://u@/app?host=/run/p", tmp_path / "backups", "abc123")
    assert target.name.startswith("pre-upgrade-")
    assert target.name.endswith("-abc123.dump")
    assert "--dbname=app" in target.read_text()
    assert list((tmp_path / "backups").glob("*.partial")) == []


def test_only_the_newest_copies_are_kept(tmp_path: Path) -> None:
    for number in range(8):
        (tmp_path / f"pre-upgrade-2026010{number}T000000Z-x.dump").write_text("x")
    (tmp_path / "notes.txt").write_text("not a backup")
    prune(tmp_path)
    kept = sorted(path.name for path in tmp_path.glob("pre-upgrade-*"))
    assert len(kept) == 5
    assert kept[0].startswith("pre-upgrade-20260103")
    assert (tmp_path / "notes.txt").exists()


def test_a_failed_dump_leaves_nothing_behind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_dumper(tmp_path, monkeypatch, FAILING_DUMPER)
    with pytest.raises(BackupError, match="connection refused"):
        back_up("postgresql+psycopg://u@/app", tmp_path / "backups", "abc")
    assert list((tmp_path / "backups").iterdir()) == []


def test_a_missing_pg_dump_stops_the_migration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))
    with pytest.raises(BackupError, match="not installed"):
        back_up("postgresql+psycopg://u@/app", tmp_path / "backups", "abc")


def test_the_password_variable_is_not_passed_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = '#!/bin/sh\nfor a in "$@"; do case "$a" in --file=*) f="${a#--file=}";; esac; done\n'
    script += 'echo "pw=${PGPASSWORD:-none}" > "$f"\n'
    install_dumper(tmp_path, monkeypatch, script)
    monkeypatch.setenv("PGPASSWORD", "hunter2")
    target = back_up("postgresql+psycopg://u@/app", tmp_path / "backups", "abc")
    assert target.read_text().strip() == "pw=none"


def test_a_new_database_is_not_backed_up(
    database_url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BLINDSPOT_DATA_DIR", str(tmp_path))
    migrate.get_settings.cache_clear()
    assert migrate.main() == 0
    assert not (tmp_path / "backups").exists()


def test_a_database_at_the_newest_revision_is_not_backed_up(
    database_url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    migrate.upgrade(database_url)
    monkeypatch.setenv("BLINDSPOT_DATA_DIR", str(tmp_path))
    migrate.get_settings.cache_clear()
    assert migrate.main() == 0
    assert not (tmp_path / "backups").exists()


def test_an_older_database_is_backed_up_before_it_is_migrated(
    database_url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    migrate.upgrade(database_url)
    with psycopg.connect(connection_string(database_url), autocommit=True) as connection:
        connection.execute("UPDATE alembic_version SET version_num = 'older'")
    install_dumper(tmp_path, monkeypatch, DUMPER)
    monkeypatch.setenv("BLINDSPOT_DATA_DIR", str(tmp_path))
    migrate.get_settings.cache_clear()
    order: list[str] = []
    real_back_up = migrate.back_up

    def recording_back_up(url: str, directory: Path, revision: str) -> Path:
        order.append("backup")
        return real_back_up(url, directory, revision)

    monkeypatch.setattr(migrate, "back_up", recording_back_up)
    monkeypatch.setattr(migrate, "upgrade", lambda: order.append("upgrade"))
    assert migrate.main() == 0
    assert order == ["backup", "upgrade"]
    assert [path.name.split("-")[-1] for path in (tmp_path / "backups").iterdir()] == ["older.dump"]


def test_a_failed_backup_means_no_migration(
    database_url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    migrate.upgrade(database_url)
    with psycopg.connect(connection_string(database_url), autocommit=True) as connection:
        connection.execute("UPDATE alembic_version SET version_num = 'older'")
    install_dumper(tmp_path, monkeypatch, FAILING_DUMPER)
    monkeypatch.setenv("BLINDSPOT_DATA_DIR", str(tmp_path))
    migrate.get_settings.cache_clear()
    upgraded: list[bool] = []
    monkeypatch.setattr(migrate, "upgrade", lambda: upgraded.append(True))
    with pytest.raises(BackupError):
        migrate.main()
    assert upgraded == []


def test_it_waits_for_a_database_that_is_still_starting(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = iter([0.0, 1.0, 1000.0])
    monkeypatch.setattr(migrate.time, "monotonic", lambda: next(clock))
    slept: list[float] = []
    monkeypatch.setattr(migrate.time, "sleep", slept.append)
    with pytest.raises(OperationalError):
        migrate.revisions("postgresql+psycopg://u@127.0.0.1:1/none", wait=60)
    assert slept == [0.5]


def test_it_gives_up_at_once_when_not_asked_to_wait() -> None:
    started = time.monotonic()
    with pytest.raises(OperationalError):
        migrate.revisions("postgresql+psycopg://u@127.0.0.1:1/none", wait=0)
    assert time.monotonic() - started < 5
