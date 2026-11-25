"""The checks on a tool's values: each type, and the values that must never reach a command."""

from typing import Any

import pytest

from app.tools.params import Param, ToolInputError, check_param


def param(**fields: Any) -> Param:
    return Param.model_validate(fields)


@pytest.mark.parametrize(
    ("fields", "value"),
    [
        ({"type": "string"}, "hello world"),
        ({"type": "string", "pattern": "[a-z]+"}, "abc"),
        ({"type": "integer", "minimum": 1, "maximum": 10}, 10),
        ({"type": "integer"}, -5),
        ({"type": "boolean"}, True),
        ({"type": "enum", "values": ["a", "b"]}, "b"),
        ({"type": "ports"}, "80,443,8000-8100"),
        ({"type": "ports"}, "top-1000"),
        ({"type": "target"}, "shop.example.com"),
        ({"type": "target"}, "shop.example.com:8080"),
        ({"type": "target"}, "10.0.0.5"),
        ({"type": "target"}, "2001:db8::1"),
        ({"type": "target"}, "[2001:db8::1]:443"),
        ({"type": "target"}, "10.0.0.0/24"),
        ({"type": "target"}, "https://shop.example.com/search?q=1&x=2"),
        ({"type": "target"}, "http://10.0.0.5:8080/a"),
        ({"type": "file"}, "common.txt"),
        ({"type": "file"}, "lists/web/common-1.txt"),
    ],
)
def test_a_good_value_is_accepted_as_it_is(fields: dict[str, Any], value: object) -> None:
    assert check_param(param(**fields), value, "value") == value


@pytest.mark.parametrize(
    ("fields", "value", "message"),
    [
        ({"type": "string"}, 5, "must be text"),
        ({"type": "string"}, "", "between 1 and"),
        ({"type": "string"}, "x" * 201, "between 1 and 200"),
        ({"type": "string"}, "a\x00b", "control characters"),
        ({"type": "string"}, "a\nb", "control characters"),
        ({"type": "string", "pattern": "[a-z]+"}, "ABC", "not in the form"),
        ({"type": "integer"}, "5", "whole number"),
        ({"type": "integer"}, True, "whole number"),
        ({"type": "integer", "minimum": 1}, 0, "between 1 and"),
        ({"type": "integer", "maximum": 5}, 6, "between"),
        ({"type": "boolean"}, "yes", "true or false"),
        ({"type": "enum", "values": ["a"]}, "b", "one of: a"),
        ({"type": "enum", "values": ["a"]}, 1, "one of: a"),
        ({"type": "ports"}, "80;ls", "must be ports"),
        ({"type": "ports"}, "0", "outside 1 to 65535"),
        ({"type": "ports"}, "70000", "outside 1 to 65535"),
        ({"type": "ports"}, "100-90", "runs backwards"),
        ({"type": "ports"}, "80-70000", "outside 1 to 65535"),
        ({"type": "target"}, "-oN /etc/passwd", "spaces or start with a dash"),
        ({"type": "target"}, "--script=evil", "spaces or start with a dash"),
        ({"type": "target"}, "a b", "spaces or start with a dash"),
        ({"type": "target"}, "a\\b", "spaces or start with a dash"),
        ({"type": "target"}, "ftp://example.com", r"http\(s\) address"),
        ({"type": "target"}, "https://user:pw@example.com", r"http\(s\) address"),
        ({"type": "target"}, "https://", r"http\(s\) address"),
        ({"type": "target"}, "https://exa mple.com", "spaces"),
        ({"type": "target"}, "https://example.com:99999", "not a valid web address"),
        ({"type": "target"}, "https://example.com:0", "outside 1 to 65535"),
        ({"type": "target"}, "example.com;ls", "web address, a host name"),
        ({"type": "target"}, "exa_mple.com", "web address, a host name"),
        ({"type": "target"}, "[2001:db8::1", "web address, a host name"),
        ({"type": "target"}, "host:port", "web address, a host name"),
        ({"type": "target"}, "10.0.0.0/99", "not a valid address range"),
        ({"type": "target"}, "example.com/path", "not a valid address range"),
        ({"type": "file"}, "/etc/passwd", "relative file path"),
        ({"type": "file"}, "../secret", "relative file path"),
        ({"type": "file"}, "a/../b", "relative file path"),
        ({"type": "file"}, "a//b", "relative file path"),
        ({"type": "file"}, "a/./b", "relative file path"),
        ({"type": "file"}, "-rf", "relative file path"),
    ],
)
def test_a_bad_value_is_refused_with_a_reason(
    fields: dict[str, Any], value: object, message: str
) -> None:
    declared = param(**fields)
    with pytest.raises(ToolInputError, match=message):
        check_param(declared, value, "value")


def test_a_list_checks_every_item_and_its_length() -> None:
    hosts = param(type="target", many=True, max_items=2)
    assert check_param(hosts, ["a.example.com", "b.example.com"], "hosts") == [
        "a.example.com",
        "b.example.com",
    ]
    assert check_param(hosts, ("a.example.com",), "hosts") == ["a.example.com"]
    for bad in ([], ["a", "b", "c"], "a.example.com", None):
        with pytest.raises(ToolInputError, match="list of 1 to 2 values"):
            check_param(hosts, bad, "hosts")
    with pytest.raises(ToolInputError, match="spaces"):
        check_param(hosts, ["a.example.com", "-x"], "hosts")


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"type": "enum"}, "needs a list of values"),
        ({"type": "enum", "values": ["a", "a"]}, "each once"),
        ({"type": "string", "values": ["a"]}, "only an enum has values"),
        ({"type": "string", "minimum": 1}, "only an integer"),
        ({"type": "string", "maximum": 1}, "only an integer"),
        ({"type": "integer", "minimum": 5, "maximum": 1}, "minimum is above"),
        ({"type": "integer", "pattern": "a"}, "only a string has a pattern"),
        ({"type": "string", "pattern": "("}, "not a valid regular expression"),
        ({"type": "string", "max_length": 0}, "max_length"),
        ({"type": "string", "max_length": 5000}, "max_length"),
        ({"type": "string", "max_items": 0}, "max_items"),
        ({"type": "integer", "many": True}, "a list must be"),
        ({"type": "string", "many": True, "default": "a"}, "a list must be"),
        ({"type": "string", "required": True, "default": "a"}, "required has no default"),
        ({"type": "integer", "default": "a"}, "whole number"),
        ({"type": "integer", "default": 5, "maximum": 3}, "between"),
    ],
)
def test_a_parameter_that_contradicts_itself_is_refused(
    fields: dict[str, Any], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        param(**fields)
