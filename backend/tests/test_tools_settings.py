"""How tools are run: the defaults, a tool's own choices, where a tool would run and why it
cannot, the Test button, and what the settings do to a call."""

from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient
from tests.conftest import add_account, another_browser, app_of
from tests.tools_helpers import CUSTOM, NMAP, manifest

from app.db.events import connection_string
from app.tools import registry, settings_routes
from app.tools.manifest import Manifest
from app.tools.registry import Tool, fingerprint
from app.tools.settings import DockerState, SystemProbe
from app.tools.settings_routes import get_probe

BUILTIN: dict[str, Any] = {
    "id": "b.headers",
    "name": "Headers",
    "tier": "builtin",
    "execution": "builtin",
    "handler": "headers",
    "risk": "passive",
    "explain": "Reads the security headers of a page.",
    "could_go_wrong": "It makes one request.",
}
PACK: dict[str, Any] = manifest(
    NMAP,
    id="p.nuclei",
    name="Nuclei",
    tier="pack",
    binary="nuclei",
    capabilities=[],
    image="ghcr.io/projectdiscovery/nuclei@sha256:" + "a" * 64,
    version={"args": ["-version"], "pattern": "([0-9.]+)"},
)
ECHO = manifest(
    CUSTOM,
    id="x.echo",
    name="Echo",
    binary="/bin/echo",
    risk="passive",
    version={"args": ["Echo version 4.5.6"], "pattern": "version ([0-9.]+)"},
    params={"url": {"type": "target", "required": True}},
    argv=["{url}"],
)


class Machine:
    """A machine for the tests: which programs it has, and whether Docker is there."""

    def __init__(self, have: dict[str, str], docker: bool = False) -> None:
        self.have = have
        self.docker_up = docker

    def locate(self, binary: str) -> str | None:
        return self.have.get(binary)

    def docker(self) -> DockerState:
        return DockerState(self.docker_up, "" if self.docker_up else "Docker is not reachable.")


@pytest.fixture(autouse=True)
def _tools(monkeypatch: pytest.MonkeyPatch) -> None:
    parsed = [Manifest.model_validate(one) for one in (NMAP, PACK, BUILTIN)]
    monkeypatch.setattr(
        registry,
        "bundled_tools",
        lambda: tuple(Tool(one, "bundled", fingerprint(one)) for one in parsed),
    )


def machine(admin: TestClient, have: dict[str, str] | None = None, *, docker: bool = False) -> None:
    found = Machine(have if have is not None else {"nmap": "/usr/bin/nmap"}, docker)
    app_of(admin).dependency_overrides[get_probe] = lambda: found


def read(admin: TestClient) -> dict[str, Any]:
    answer = admin.get("/api/tools/settings")
    assert answer.status_code == 200, answer.text
    return answer.json()


def tool(admin: TestClient, tool_id: str) -> dict[str, Any]:
    return next(one for one in read(admin)["tools"] if one["id"] == tool_id)


def set_tool(admin: TestClient, tool_id: str, **values: Any) -> Any:
    return admin.put(f"/api/tools/settings/{tool_id}", json=values)


def test_the_page_lists_every_tool_with_where_it_runs_by_default(admin: TestClient) -> None:
    machine(admin)
    page = read(admin)
    assert page["run_mode"] == "auto"
    assert page["docker"] == {"reachable": False, "note": "Docker is not reachable."}
    assert [one["id"] for one in page["tools"]] == ["b.headers", "c.nmap", "p.nuclei"]
    nmap, nuclei = tool(admin, "c.nmap"), tool(admin, "p.nuclei")
    assert nmap["effective"] == {
        "mode": "local",
        "status": "ready",
        "problem": "",
        "fell_back": False,
        "offer": None,
        "path": "/usr/bin/nmap",
    }
    assert (nmap["limits"]["timeout_s"], nmap["limits"]["max_output_mb"]) == (900, 20)
    assert nmap["limits"]["max_risk"] == "active"
    # A pack tool is not in the image, so Auto means Docker, which is not there.
    assert nuclei["effective"]["status"] == "docker_unreachable"
    assert nuclei["effective"]["mode"] is None
    assert tool(admin, "b.headers")["effective"]["mode"] == "builtin"


def test_a_tool_whose_program_is_missing_says_so_and_does_not_move(admin: TestClient) -> None:
    machine(admin, {}, docker=True)
    found = tool(admin, "c.nmap")["effective"]
    assert found["mode"] is None
    assert found["status"] == "binary_not_found"
    assert found["problem"] == "The program nmap was not found."
    # Docker works and the tool has an image: offered, never taken.
    assert tool(admin, "p.nuclei")["effective"]["mode"] == "docker"
    set_tool(admin, "c.nmap", image="ghcr.io/x/nmap@sha256:" + "b" * 64)
    assert tool(admin, "c.nmap")["effective"]["offer"] == "docker"
    assert tool(admin, "c.nmap")["effective"]["mode"] is None


def test_the_default_decides_and_only_prefer_defaults_use_the_other_way(admin: TestClient) -> None:
    machine(admin, {"nmap": "/usr/bin/nmap", "nuclei": "/opt/nuclei"}, docker=False)
    assert (
        admin.put("/api/tools/settings/default", json={"mode": "prefer_docker"}).status_code == 200
    )
    assert read(admin)["run_mode"] == "prefer_docker"
    chosen = tool(admin, "p.nuclei")["effective"]
    assert (chosen["mode"], chosen["fell_back"]) == ("local", True)
    admin.put("/api/tools/settings/default", json={"mode": "docker_only"})
    refused = tool(admin, "p.nuclei")["effective"]
    assert (refused["mode"], refused["status"], refused["offer"]) == (
        None,
        "docker_unreachable",
        "local",
    )
    admin.put("/api/tools/settings/default", json={"mode": "prefer_local"})
    assert tool(admin, "c.nmap")["effective"]["fell_back"] is False
    machine(admin, {}, docker=True)
    fell = tool(admin, "p.nuclei")["effective"]
    assert (fell["mode"], fell["fell_back"]) == ("docker", True)
    assert admin.put("/api/tools/settings/default", json={"mode": "maybe"}).status_code == 422


def test_a_tool_with_its_own_mode_is_never_moved(admin: TestClient) -> None:
    machine(admin, {"nmap": "/usr/bin/nmap"}, docker=True)
    admin.put("/api/tools/settings/default", json={"mode": "prefer_local"})
    set_tool(admin, "c.nmap", mode="docker")
    # Docker is up but nmap has no image; the program being there changes nothing.
    own = tool(admin, "c.nmap")["effective"]
    assert (own["mode"], own["status"], own["offer"]) == (None, "image_missing", "local")
    set_tool(admin, "c.nmap", mode="docker", image="ghcr.io/x/nmap@sha256:" + "c" * 64)
    assert tool(admin, "c.nmap")["effective"]["mode"] == "docker"


def test_a_damaged_default_counts_as_auto(admin: TestClient, database_url: str) -> None:
    machine(admin)
    admin.put("/api/tools/settings/default", json={"mode": "docker_only"})
    with psycopg.connect(connection_string(database_url), autocommit=True) as connection:
        connection.execute(
            "UPDATE app_setting SET value = '\"nonsense\"' WHERE key = 'tools.run_mode'"
        )
    assert read(admin)["run_mode"] == "auto"


def test_settings_persist_replace_and_reset(admin: TestClient) -> None:
    machine(admin)
    answer = set_tool(
        admin,
        "c.nmap",
        binary_path="/opt/tools/nmap",
        cpus="1.5",
        memory_mb=512,
        timeout_s=300,
        max_output_mb=5,
        rate_per_s=20,
        max_risk="passive",
    )
    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert body["binary_path"] == "/opt/tools/nmap"
    assert body["default_binary"] == "nmap"
    assert body["limits"] == {
        "cpus": 1.5,
        "memory_mb": 512,
        "timeout_s": 300,
        "max_output_mb": 5,
        "rate_per_s": 20,
        "max_risk": "passive",
    }
    assert body["effective"]["problem"] == "The program /opt/tools/nmap was not found."
    assert tool(admin, "c.nmap")["overrides"]["rate_per_s"] == 20
    # A new request replaces everything: what is left out is the manifest's again.
    again = set_tool(admin, "c.nmap", enabled=False).json()
    assert again["limits"]["timeout_s"] == 900
    assert again["limits"]["max_risk"] == "active"
    assert again["effective"]["status"] == "disabled"
    assert admin.delete("/api/tools/settings/c.nmap").status_code == 204
    assert tool(admin, "c.nmap")["enabled"] is True
    assert admin.delete("/api/tools/settings/c.nmap").status_code == 204


def test_what_cannot_be_set_is_refused(admin: TestClient) -> None:
    machine(admin)
    assert set_tool(admin, "c.missing").status_code == 404
    assert admin.delete("/api/tools/settings/c.missing").status_code == 404
    assert set_tool(admin, "c.nmap", binary_path=None).status_code == 200
    assert set_tool(admin, "c.nmap", binary_path="/bin/sh").status_code == 422
    assert set_tool(admin, "c.nmap", binary_path="/opt/../bin/nmap").status_code == 422
    assert set_tool(admin, "c.nmap", binary_path="/usr/bin/python3").status_code == 422
    assert set_tool(admin, "c.nmap", mode="docker", binary_path="/opt/nmap").status_code == 422
    assert (
        set_tool(admin, "c.nmap", mode="local", image="x/y@sha256:" + "d" * 64).status_code == 422
    )
    assert set_tool(admin, "c.nmap", image="nmap:latest").status_code == 422
    assert set_tool(admin, "c.nmap", timeout_s=0).status_code == 422
    assert set_tool(admin, "c.nmap", cpus="0").status_code == 422
    assert set_tool(admin, "c.nmap", memory_mb=1).status_code == 422
    assert set_tool(admin, "c.nmap", mode="remote").status_code == 422
    assert set_tool(admin, "c.nmap", surprise=True).status_code == 422
    assert set_tool(admin, "c.nmap", max_risk="intrusive").status_code == 422
    assert set_tool(admin, "b.headers", mode="docker").status_code == 422
    assert set_tool(admin, "b.headers", binary_path="/opt/x").status_code == 422
    # A built-in tool can still be switched off and limited.
    assert set_tool(admin, "b.headers", enabled=False, timeout_s=5).status_code == 200


def test_a_viewer_can_read_and_change_nothing(admin: TestClient) -> None:
    machine(admin)
    add_account(admin, "vera", "viewer")
    viewer = another_browser(admin, "vera")
    app_of(admin).dependency_overrides[get_probe] = lambda: Machine({"nmap": "/usr/bin/nmap"})
    assert viewer.get("/api/tools/settings").status_code == 200
    assert (
        viewer.put("/api/tools/settings/default", json={"mode": "docker_only"}).status_code == 403
    )
    assert viewer.put("/api/tools/settings/c.nmap", json={"enabled": False}).status_code == 403
    assert viewer.delete("/api/tools/settings/c.nmap").status_code == 403
    assert viewer.post("/api/tools/settings/c.nmap/test").status_code == 403
    assert read(admin)["run_mode"] == "auto"
    assert tool(admin, "c.nmap")["enabled"] is True


def test_every_change_is_in_the_audit_trail(admin: TestClient, database_url: str) -> None:
    machine(admin)
    admin.put("/api/tools/settings/default", json={"mode": "prefer_local"})
    set_tool(admin, "c.nmap", rate_per_s=5)
    admin.delete("/api/tools/settings/c.nmap")
    with psycopg.connect(connection_string(database_url)) as connection:
        found = [
            row[0]
            for row in connection.execute(
                "SELECT action FROM audit_event WHERE action LIKE 'tool.settings.%' ORDER BY id"
            )
        ]
    assert found == ["tool.settings.default", "tool.settings.update", "tool.settings.reset"]


def custom(admin: TestClient) -> None:
    assert admin.post("/api/tools/custom", json=ECHO).status_code == 201


def test_test_runs_the_version_check_and_shows_the_command(admin: TestClient) -> None:
    machine(admin, {"/bin/echo": "/bin/echo"})
    custom(admin)
    answer = admin.post("/api/tools/settings/x.echo/test")
    assert answer.status_code == 200, answer.text
    assert answer.json() | {"duration_ms": 0} == {
        "mode": "local",
        "command": ["echo", "Echo version 4.5.6"],
        "exit_code": 0,
        "output": "Echo version 4.5.6\n",
        "duration_ms": 0,
        "version": "4.5.6",
        "timed_out": False,
    }


def test_test_hides_a_secret_in_what_the_tool_printed(admin: TestClient) -> None:
    machine(admin, {"/bin/echo": "/bin/echo"})
    admin.post(
        "/api/tools/custom",
        json=manifest(ECHO, version={"args": ["password=hunter2hunter2"], "pattern": "(zzz)"}),
    )
    shown = admin.post("/api/tools/settings/x.echo/test").json()
    assert "hunter2" not in shown["output"]
    assert shown["version"] is None


def test_test_stops_a_program_that_runs_too_long(
    admin: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings_routes, "TEST_SECONDS", 0.05)
    machine(admin, {"/bin/sleep": "/bin/sleep"})
    admin.post(
        "/api/tools/custom",
        json=manifest(ECHO, binary="/bin/sleep", version={"args": ["5"]}),
    )
    shown = admin.post("/api/tools/settings/x.echo/test").json()
    assert (shown["timed_out"], shown["exit_code"], shown["output"], shown["version"]) == (
        True,
        None,
        "",
        None,
    )


def test_test_does_not_switch_to_another_way_or_run_what_is_not_ready(admin: TestClient) -> None:
    machine(admin, {}, docker=True)
    custom(admin)
    refused = admin.post("/api/tools/settings/x.echo/test")
    assert refused.status_code == 409
    assert refused.json()["code"] == "cannot_test"
    assert "was not found" in refused.json()["detail"]
    # Docker is the way, and a Docker test needs the runner that does not exist yet.
    docked = admin.post("/api/tools/settings/p.nuclei/test")
    assert docked.status_code == 409
    set_tool(admin, "p.nuclei", mode="docker")
    assert admin.post("/api/tools/settings/p.nuclei/test").status_code == 409
    assert admin.post("/api/tools/settings/b.headers/test").status_code == 409
    set_tool(admin, "x.echo", enabled=False)
    assert (
        admin.post("/api/tools/settings/x.echo/test").json()["detail"]
        == "This tool is switched off."
    )
    assert admin.post("/api/tools/settings/c.missing/test").status_code == 404


def test_a_tool_without_a_version_check_cannot_be_tested(admin: TestClient) -> None:
    machine(admin, {"/bin/echo": "/bin/echo"})
    document = manifest(ECHO)
    del document["version"]
    admin.post("/api/tools/custom", json=document)
    refused = admin.post("/api/tools/settings/x.echo/test")
    assert (refused.status_code, refused.json()["code"]) == (409, "no_version_check")


def test_the_system_probe_looks_at_files_and_has_no_docker() -> None:
    probe = SystemProbe()
    assert probe.locate("/bin/echo") == "/bin/echo"
    assert probe.locate("/etc/hostname") is None  # a file, but not a program
    assert probe.locate("/no/such/program") is None
    assert probe.locate("sh") is not None
    assert probe.locate("no-such-program-anywhere") is None
    assert probe.docker().reachable is False
    assert get_probe().docker().reachable is False


def test_deleting_a_custom_tool_takes_its_settings_with_it(admin: TestClient) -> None:
    machine(admin, {"/bin/echo": "/bin/echo"})
    custom(admin)
    set_tool(admin, "x.echo", rate_per_s=3)
    assert admin.delete("/api/tools/custom/x.echo").status_code == 204
    custom(admin)
    assert tool(admin, "x.echo")["overrides"]["rate_per_s"] is None
    admin.delete("/api/tools/custom/x.echo")
    # A custom tool that never had settings is deleted all the same.
    custom(admin)
    assert admin.delete("/api/tools/custom/x.echo").status_code == 204
