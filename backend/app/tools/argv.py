"""From a tool and the values an agent gave to the argument list the runner will execute.

This is the only place a command line is made. It checks every value against the parameter's type
(see `params.py`), fills in defaults, refuses values the manifest does not know about, and builds
a list of arguments. A value fills exactly one argument (or, for a list, one argument each): it
is never split, never joined into a string for a shell, and never allowed to begin with a dash
where it would be read as an option. The runner executes the list directly, without a shell.
"""

from dataclasses import dataclass

from app.tools.manifest import Manifest, When
from app.tools.params import Param, Scalar, ToolInputError, check_param
from app.tools.template import Piece, parse_template, starts_with_value

MAX_ARGUMENTS = 2000
MAX_ARGUMENT_BYTES = 8192
MAX_TOTAL_BYTES = 128 * 1024

Value = Scalar | list[Scalar]


@dataclass(frozen=True)
class Call:
    """A tool call that has been checked: what to run, and what it will touch. `targets` is every
    value of every target parameter, for the scope guard."""

    tool: str
    argv: tuple[str, ...]
    values: dict[str, Value]
    targets: tuple[str, ...]


def checked_values(manifest: Manifest, given: dict[str, object]) -> dict[str, Value]:
    """Every parameter's value, checked, with defaults filled in. A value the manifest does not
    know about is an error, not something to ignore."""
    unknown = sorted(set(given) - set(manifest.params))
    if unknown:
        raise ToolInputError(f"{unknown[0]} is not a parameter of {manifest.id}")
    values: dict[str, Value] = {}
    for name, param in manifest.params.items():
        raw = given.get(name)
        if raw is None:
            raw = param.default
        if raw is None:
            if param.required:
                raise ToolInputError(f"{name} is required")
            continue
        values[name] = check_param(param, raw, name)
    return values


def _is_set(param: Param, value: Value | None, condition: When) -> bool:
    if value is None or value is False:
        return False
    if condition.equals is None:
        return True
    return not param.many and str(value) == str(condition.equals)


def _expand(pieces: tuple[Piece, ...], values: dict[str, Value]) -> list[str]:
    """One template as arguments: one, or one for each value of a spread list."""
    if len(pieces) == 1 and pieces[0].spread:
        listed = values[pieces[0].name or ""]
        return [str(item) for item in listed] if isinstance(listed, list) else []
    parts = [piece.literal if piece.name is None else str(values[piece.name]) for piece in pieces]
    return ["".join(parts)]


def _refuse_options(pieces: tuple[Piece, ...], arguments: list[str]) -> None:
    """A value at the start of an argument must not look like an option."""
    if starts_with_value(pieces):
        for argument in arguments:
            if argument.startswith("-"):
                raise ToolInputError("a value must not start with a dash")


def _arguments(manifest: Manifest, values: dict[str, Value]) -> list[str]:
    arguments: list[str] = []
    for item in manifest.argv:
        if isinstance(item, When):
            if not _is_set(manifest.params[item.when], values.get(item.when), item):
                continue
            templates = item.args
        else:
            templates = [item]
        for template in templates:
            pieces = parse_template(template)
            expanded = _expand(pieces, values)
            _refuse_options(pieces, expanded)
            arguments.extend(expanded)
    return arguments


def _check_size(argv: list[str]) -> None:
    if len(argv) > MAX_ARGUMENTS or sum(len(argument) for argument in argv) > MAX_TOTAL_BYTES:
        raise ToolInputError("the command line would be too long")
    if any(len(argument.encode()) > MAX_ARGUMENT_BYTES for argument in argv):
        raise ToolInputError("one argument would be too long")


def _targets(manifest: Manifest, values: dict[str, Value]) -> tuple[str, ...]:
    found: list[str] = []
    for name in manifest.target_params():
        value = values.get(name)
        if isinstance(value, list):
            found.extend(str(item) for item in value)
        elif value is not None:
            found.append(str(value))
    return tuple(found)


def build_call(manifest: Manifest, given: dict[str, object]) -> Call:
    """Check a call and build its argument list. Raises ToolInputError, with a message that is
    safe to show, when the values do not fit the manifest."""
    values = checked_values(manifest, given)
    argv: list[str] = []
    if manifest.execution == "process" and manifest.binary:
        argv = [manifest.binary, *_arguments(manifest, values)]
        _check_size(argv)
    return Call(manifest.id, tuple(argv), values, _targets(manifest, values))
