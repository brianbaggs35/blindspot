"""The typed values a tool takes, and the checks that make each one safe to put on a command
line.

A value is checked against its declared type before it reaches an argument list: no control
characters (so no NUL and no new line), a length limit, and for a port list, a target or a file
the shape that kind of value has. Nothing here ever runs a command or looks at the network, so
whether a target is allowed at all is decided by the scope guard, not here.
"""

import ipaddress
import re
from enum import StrEnum
from typing import Annotated, Self, cast
from urllib.parse import urlsplit

from pydantic import StringConstraints, model_validator

from app.methodology.spec import Line, Strict

ParamName = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,31}$")]
EnumValue = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9._:/+-]{1,64}$")]

Scalar = str | int | bool

MAX_TEXT = 4000
MAX_TARGET = 300
MAX_PORTS = 200
MAX_FILE = 200
INT_LIMIT = 2**31 - 1
_UNSAFE = re.compile(r"[\x00-\x20\x7f\\]")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_LABEL = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")
_PORT_OR_RANGE = r"\d{1,5}(?:-\d{1,5})?"
_PORTS = re.compile(rf"^(?:top-\d{{1,5}}|{_PORT_OR_RANGE}(?:,{_PORT_OR_RANGE})*)$", re.ASCII)
_PORT_SUFFIX = re.compile(r"(?::\d{1,5})?", re.ASCII)
_PORT_ONLY = re.compile(r"\d{1,5}", re.ASCII)
_FILE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")


class ToolInputError(ValueError):
    """A value is not acceptable. The message names the value and is safe to show to anyone."""


class ParamType(StrEnum):
    """What a value is."""

    STRING = "string"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    ENUM = "enum"
    PORTS = "ports"
    TARGET = "target"
    FILE = "file"


# The types that may be given as a list.
LISTABLE = (ParamType.STRING, ParamType.ENUM, ParamType.TARGET, ParamType.FILE)


class Param(Strict):
    """One value a tool takes."""

    type: ParamType
    description: Line | None = None
    required: bool = False
    default: str | int | bool | None = None
    many: bool = False
    max_items: int = 50
    values: list[EnumValue] | None = None
    minimum: int | None = None
    maximum: int | None = None
    pattern: Annotated[str, StringConstraints(max_length=200)] | None = None
    max_length: int = 200

    @model_validator(mode="after")
    def _is_consistent(self) -> Self:
        problem = _shape_problem(self)
        if problem:
            raise ValueError(problem)
        if self.default is not None:
            try:
                check_param(self, self.default, "default")
            except ToolInputError as error:
                raise ValueError(str(error)) from None
        return self


def _values_problem(param: Param) -> str | None:
    if param.type is ParamType.ENUM:
        if not param.values or len(set(param.values)) != len(param.values):
            return "an enum needs a list of values, each once"
    elif param.values is not None:
        return "only an enum has values"
    return None


def _range_problem(param: Param) -> str | None:
    if param.type is not ParamType.INTEGER and (
        param.minimum is not None or param.maximum is not None
    ):
        return "only an integer has a minimum or a maximum"
    if param.minimum is not None and param.maximum is not None and param.minimum > param.maximum:
        return "the minimum is above the maximum"
    return None


def _pattern_problem(param: Param) -> str | None:
    if param.pattern is None:
        return None
    if param.type is not ParamType.STRING:
        return "only a string has a pattern"
    try:
        re.compile(param.pattern)
    except re.error:
        return "the pattern is not a valid regular expression"
    return None


def _limits_problem(param: Param) -> str | None:
    if not 1 <= param.max_length <= MAX_TEXT:
        return f"max_length must be between 1 and {MAX_TEXT}"
    if not 1 <= param.max_items <= 1000:
        return "max_items must be between 1 and 1000"
    if param.many and (param.type not in LISTABLE or param.default is not None):
        return "a list must be a string, enum, target or file, and has no default"
    if param.required and param.default is not None:
        return "a value that is required has no default"
    return None


def _shape_problem(param: Param) -> str | None:
    """The first thing wrong with how a parameter is declared, as one message, or None."""
    for check in (_values_problem, _range_problem, _pattern_problem, _limits_problem):
        if problem := check(param):
            return problem
    return None


def _text(raw: object, name: str, limit: int) -> str:
    if not isinstance(raw, str):
        raise ToolInputError(f"{name} must be text")
    if not raw or len(raw) > limit:
        raise ToolInputError(f"{name} must be between 1 and {limit} characters")
    if _CONTROL.search(raw):
        raise ToolInputError(f"{name} must not contain control characters")
    return raw


def _string(param: Param, raw: object, name: str) -> Scalar:
    text = _text(raw, name, param.max_length)
    if param.pattern is not None and re.fullmatch(param.pattern, text) is None:
        raise ToolInputError(f"{name} is not in the form this tool accepts")
    return text


def _integer(param: Param, raw: object, name: str) -> Scalar:
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise ToolInputError(f"{name} must be a whole number")
    low = -INT_LIMIT if param.minimum is None else param.minimum
    high = INT_LIMIT if param.maximum is None else param.maximum
    if not low <= raw <= high:
        raise ToolInputError(f"{name} must be between {low} and {high}")
    return raw


def _boolean(_param: Param, raw: object, name: str) -> Scalar:
    if not isinstance(raw, bool):
        raise ToolInputError(f"{name} must be true or false")
    return raw


def _enum(param: Param, raw: object, name: str) -> Scalar:
    if not isinstance(raw, str) or raw not in (param.values or []):
        raise ToolInputError(f"{name} must be one of: {', '.join(param.values or [])}")
    return raw


def _port_number(text: str, name: str) -> int:
    number = int(text)
    if not 1 <= number <= 65535:
        raise ToolInputError(f"{name} has a port outside 1 to 65535")
    return number


def _ports(_param: Param, raw: object, name: str) -> Scalar:
    text = _text(raw, name, MAX_PORTS)
    if _PORTS.fullmatch(text) is None:
        raise ToolInputError(f"{name} must be ports like 80,443,8000-8100 or top-1000")
    for part in text.removeprefix("top-").split(","):
        low, _, high = part.partition("-")
        first = _port_number(low, name)
        if high and _port_number(high, name) < first:
            raise ToolInputError(f"{name} has a range that runs backwards")
    return text


def _host_ok(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return len(host) <= 253 and all(_LABEL.fullmatch(label) for label in host.split("."))
    return True


def _address_with_port(text: str) -> str:
    """`host`, `host:port`, `[v6]`, `[v6]:port` or a bare IPv6 address: the host part."""
    if text.startswith("["):
        host, closed, rest = text[1:].partition("]")
        return host if closed and _PORT_SUFFIX.fullmatch(rest) else ""
    if text.count(":") > 1:
        return text
    host, _, port = text.partition(":")
    return host if port == "" or _PORT_ONLY.fullmatch(port) else ""


def _check_url(text: str, name: str) -> None:
    try:
        parts = urlsplit(text)
        port = parts.port
    except ValueError:
        raise ToolInputError(f"{name} is not a valid web address") from None
    host = parts.hostname or ""
    if parts.scheme not in ("http", "https") or parts.username is not None or not _host_ok(host):
        raise ToolInputError(f"{name} must be an http(s) address with a host and no user name")
    if port == 0:
        raise ToolInputError(f"{name} has a port outside 1 to 65535")


def _target(_param: Param, raw: object, name: str) -> Scalar:
    text = _text(raw, name, MAX_TARGET)
    if _UNSAFE.search(text) or text.startswith("-"):
        raise ToolInputError(f"{name} must not contain spaces or start with a dash")
    if "://" in text:
        _check_url(text, name)
    elif "/" in text:
        if not _is_network(text):
            raise ToolInputError(f"{name} is not a valid address range")
    elif not _host_ok(_address_with_port(text)):
        raise ToolInputError(f"{name} must be a web address, a host name, an address or a range")
    return text


def _is_network(text: str) -> bool:
    try:
        ipaddress.ip_network(text, strict=False)
    except ValueError:
        return False
    return True


def _file(_param: Param, raw: object, name: str) -> Scalar:
    text = _text(raw, name, MAX_FILE)
    segments = text.split("/")
    if _FILE.fullmatch(text) is None or ".." in segments or "" in segments or "." in segments:
        raise ToolInputError(f"{name} must be a relative file path with no '..'")
    return text


_CHECKS = {
    ParamType.STRING: _string,
    ParamType.INTEGER: _integer,
    ParamType.BOOLEAN: _boolean,
    ParamType.ENUM: _enum,
    ParamType.PORTS: _ports,
    ParamType.TARGET: _target,
    ParamType.FILE: _file,
}


def check_param(param: Param, raw: object, name: str) -> Scalar | list[Scalar]:
    """The value, checked against its type: one value, or a list of them for a list parameter."""
    check = _CHECKS[param.type]
    if not param.many:
        return check(param, raw, name)
    items = cast("list[object]", raw) if isinstance(raw, list | tuple) else []
    if not 1 <= len(items) <= param.max_items:
        raise ToolInputError(f"{name} must be a list of 1 to {param.max_items} values")
    return [check(param, item, name) for item in items]
