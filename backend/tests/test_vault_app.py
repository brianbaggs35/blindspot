"""The app opens the vault when it starts, and the key command."""

import runpy
import sys

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.vault import VaultError
from app.vault.__main__ import main


def test_the_app_starts_with_a_vault() -> None:
    app = create_app()
    with TestClient(app):
        assert app.state.vault is not None


def test_the_app_does_not_start_with_a_short_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BLINDSPOT_SECRET_KEY", "short")
    with pytest.raises(VaultError), TestClient(create_app()):
        pass


def test_generate_prints_a_key(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["generate"]) == 0
    assert len(capsys.readouterr().out.strip()) == 96


def test_rotate_says_how_many_values_it_sealed(
    database_url: str, capsys: pytest.CaptureFixture[str]
) -> None:
    from app.db.migrate import upgrade  # noqa: PLC0415

    upgrade(database_url)
    assert main(["rotate"]) == 0
    assert capsys.readouterr().out == "0 values sealed with the current key.\n"


def test_rotate_reports_a_key_problem(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("BLINDSPOT_SECRET_KEY", "short")
    assert main(["rotate"]) == 1
    assert "at least 32" in capsys.readouterr().err


def test_an_unknown_command_prints_usage(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["nonsense"]) == 2
    assert "usage" in capsys.readouterr().err


def test_rotate_reports_a_value_that_cannot_be_opened(
    database_url: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def refuse(*_: object) -> int:
        raise VaultError("The value was sealed with a key this vault does not have.")

    monkeypatch.setattr("app.vault.__main__.rotate", refuse)
    assert main(["rotate"]) == 1
    assert "does not have" in capsys.readouterr().err


def test_running_the_module_exits_with_the_status(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["app.vault", "generate"])
    monkeypatch.delitem(sys.modules, "app.vault.__main__")
    with pytest.raises(SystemExit) as stopped:
        runpy.run_module("app.vault", run_name="__main__")
    assert stopped.value.code == 0
    assert len(capsys.readouterr().out.strip()) == 96
