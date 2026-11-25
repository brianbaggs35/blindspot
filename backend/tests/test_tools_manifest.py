"""The tool manifest: what it accepts, and every mistake it refuses to load."""

from typing import Any

import pytest
from pydantic import ValidationError
from tests.tools_helpers import CUSTOM, NMAP, manifest

from app.tools.manifest import Manifest
from app.tools.template import parse_template, starts_with_value


def load(document: dict[str, Any]) -> Manifest:
    return Manifest.model_validate(document)


def test_the_example_manifests_are_valid() -> None:
    nmap = load(NMAP)
    assert nmap.target_params() == ["targets"]
    assert nmap.risk.value == "active"
    custom = load(CUSTOM | {"tier": "custom"})
    assert custom.target_params() == ["url"]
    assert custom.tier.value == "custom"


def test_a_built_in_tool_has_a_handler_and_no_command() -> None:
    builtin = load(
        manifest(
            NMAP,
            id="b.http",
            tier="builtin",
            execution="builtin",
            binary=None,
            handler="http_client",
            capabilities=[],
            argv=[],
            version=None,
            params={"url": {"type": "target", "required": True}},
        )
    )
    assert builtin.execution == "builtin"


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"binary": None}, "has a binary and no handler"),
        ({"handler": "x_run"}, "has a binary and no handler"),
        ({"binary": "bash"}, "a shell"),
        ({"binary": "/usr/bin/env"}, "a shell"),
        ({"binary": "BASH"}, "pattern"),
        ({"binary": "../nmap"}, "pattern"),
        ({"id": "x.nmap"}, "only custom tools use ids that start with x"),
        ({"tier": "custom"}, "only custom tools use ids that start with x"),
        ({"id": "x.curl", "tier": "custom", "binary": "python3"}, "not an interpreter"),
        ({"id": "x.curl", "tier": "custom", "binary": "/usr/bin/python3.14"}, "not an interpreter"),
        ({"id": "x.curl", "tier": "custom", "binary": "curl"}, "no capabilities"),
        ({"capabilities": ["NET_RAW", "NET_RAW"]}, "each capability is listed once"),
        ({"capabilities": ["SYS_ADMIN"]}, "Input should be"),
        ({"risk": "harmless"}, "Input should be"),
        ({"execution": "shell"}, "pattern"),
        ({"timeout_s": 0}, "greater than or equal to 1"),
        ({"max_output_mb": 9999}, "less than or equal to 512"),
        ({"image": "nmap:latest"}, "pattern"),
        ({"surprise": 1}, "Extra inputs are not permitted"),
        ({"id": "nmap"}, "pattern"),
    ],
)
def test_a_manifest_that_is_wrong_is_refused(changes: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        load(manifest(NMAP, **changes))


def test_a_built_in_tool_cannot_also_run_a_program() -> None:
    builtin = manifest(
        NMAP,
        id="b.http",
        tier="builtin",
        execution="builtin",
        handler="http_client",
        capabilities=[],
        params={},
        argv=[],
        version=None,
        binary=None,
    )
    load(builtin)
    for extra in ({"binary": "nmap"}, {"argv": ["-v"]}, {"image": "r/x@sha256:" + "a" * 64}):
        with pytest.raises(ValidationError, match="has a handler and nothing else"):
            load(builtin | extra)
    with pytest.raises(ValidationError, match="has a handler and nothing else"):
        load(builtin | {"version": {}})
    with pytest.raises(ValidationError, match="has a handler and nothing else"):
        load(builtin | {"handler": None})


def with_argv(*argv: Any, **params: Any) -> dict[str, Any]:
    return manifest(NMAP, argv=list(argv), params=params, version=None)


@pytest.mark.parametrize(
    ("document", "message"),
    [
        (with_argv("{missing}", targets={"type": "target", "required": True}), "not a parameter"),
        (with_argv("{flag}", flag={"type": "boolean"}), "only be used in a when"),
        (
            with_argv("{names}", names={"type": "string", "many": True, "required": True}),
            "is a list",
        ),
        (with_argv("{name...}", name={"type": "string", "required": True}), "is a list"),
        (
            with_argv("a{names...}", names={"type": "string", "many": True, "required": True}),
            "whole argument",
        ),
        (with_argv("{name}", name={"type": "string"}), "may be missing"),
        (with_argv("-x", name={"type": "string", "required": True}), "is not used in any argument"),
        (with_argv("a{b", name={"type": "string", "required": True}), "not part of a placeholder"),
        (with_argv("a}b", name={"type": "string", "required": True}), "not part of a placeholder"),
        (with_argv("a\x00b"), "control characters"),
        (with_argv("x" * 301), "too long"),
        (with_argv({"when": "nope", "args": ["-x"]}), "no such parameter"),
        (
            with_argv(
                {"when": "scan", "equals": "udp", "args": ["-sU"]},
                scan={"type": "enum", "values": ["tcp"]},
            ),
            "not one of its values",
        ),
        (
            with_argv(
                {"when": "names", "equals": "a", "args": ["-x"]},
                names={"type": "string", "many": True},
            ),
            "cannot be compared",
        ),
        (
            manifest(NMAP, version={"args": ["{ports}"]}),
            "version check cannot use parameters",
        ),
        (manifest(NMAP, version={"pattern": "("}), "not a valid regular expression"),
        (manifest(NMAP, version={"pattern": "a|b"}), "exactly one group"),
    ],
)
def test_an_argument_list_that_does_not_fit_its_parameters_is_refused(
    document: dict[str, Any], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        load(document)


def test_a_when_may_use_its_own_optional_parameter() -> None:
    load(with_argv({"when": "level", "args": ["--level={level}"]}, level={"type": "integer"}))


def test_a_template_is_understood_piece_by_piece() -> None:
    pieces = parse_template("--rate={rate}")
    assert [(piece.literal, piece.name) for piece in pieces] == [("--rate=", None), ("", "rate")]
    assert not starts_with_value(pieces)
    assert starts_with_value(parse_template("{target}:80"))
    assert not starts_with_value(parse_template(""))
    assert [piece.literal for piece in parse_template("{{literal}}")] == ["{", "literal", "}"]
    spread = parse_template("{hosts...}")
    assert spread[0].spread
    assert spread[0].name == "hosts"
