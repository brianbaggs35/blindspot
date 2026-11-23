"""A copy of the database, made with pg_dump before a migration changes it."""

import os
import shutil
import subprocess  # nosec B404  # runs pg_dump with an argument list and no shell
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import make_url

KEEP = 5
PREFIX = "pre-upgrade-"


class BackupError(RuntimeError):
    """The copy could not be made, so the migration must not go ahead."""


def pg_dump_arguments(url: str, target: Path) -> list[str]:
    """The pg_dump command for a database address (a TCP host or a unix socket directory)."""
    parsed = make_url(url)
    host = parsed.query.get("host") or parsed.host
    arguments = ["--format=custom", "--no-password", f"--file={target}"]
    if host:
        arguments.append(f"--host={host}")
    if parsed.port:
        arguments.append(f"--port={parsed.port}")
    if parsed.username:
        arguments.append(f"--username={parsed.username}")
    arguments.append(f"--dbname={parsed.database}")
    return arguments


def prune(directory: Path, keep: int = KEEP) -> None:
    """Keep the newest copies and delete the rest."""
    for old in sorted(directory.glob(f"{PREFIX}*.dump"))[:-keep]:
        old.unlink()


def back_up(url: str, directory: Path, revision: str) -> Path:
    """Dump the database into `directory`, named for the revision it is at. The copy is written
    under a temporary name and renamed when complete, so a half-written file is never kept."""
    pg_dump = shutil.which("pg_dump")
    if pg_dump is None:
        raise BackupError("pg_dump is not installed, so the database cannot be backed up first")
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = directory / f"{PREFIX}{stamp}-{revision}.dump"
    partial = target.with_suffix(".partial")
    env = {key: value for key, value in os.environ.items() if key != "PGPASSWORD"}
    result = subprocess.run(  # noqa: S603  # nosec B603  # no shell; the arguments are a list built from settings
        [pg_dump, *pg_dump_arguments(url, partial)],
        capture_output=True,
        text=True,
        check=False,
        env=env,
        timeout=3600,
    )
    if result.returncode != 0:
        partial.unlink(missing_ok=True)
        raise BackupError(f"pg_dump failed: {result.stderr.strip()}")
    partial.replace(target)
    prune(directory)
    return target
