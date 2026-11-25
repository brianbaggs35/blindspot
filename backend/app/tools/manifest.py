"""The tool manifest: everything the app knows about a tool, as data that is checked when it is
loaded.

A manifest says what a tool is called, how risky it is, which values it takes and how those values
become an argument list. It holds no code and no shell: the argument list is a list of templates,
and a value only ever fills one argument (see `argv.py`). Bundled manifests are YAML files in
`app/tools/bundled`; an administrator's own are stored in the database and always start with `x.`.
"""

import re
from collections.abc import Iterator
from enum import StrEnum
from typing import Annotated, Self

from pydantic import Field, StringConstraints, model_validator

from app.methodology.spec import Strict, Text, Title, ToolId, Url
from app.tools.params import Param, ParamName, ParamType
from app.tools.template import Piece, parse_template

MAX_PARAMS = 30
MAX_ARGUMENTS = 60

Handler = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,63}$")]
Binary = Annotated[
    str,
    StringConstraints(
        pattern=r"^(/[A-Za-z0-9._+-]{1,64}){1,8}$|^[a-z0-9][A-Za-z0-9._+-]{0,63}$", max_length=300
    ),
]
ParserName = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,31}$")]
Image = Annotated[
    str,
    StringConstraints(pattern=r"^[a-z0-9][a-z0-9./_-]{0,200}@sha256:[0-9a-f]{64}$"),
]
Template = Annotated[str, StringConstraints(min_length=1)]


class ToolRisk(StrEnum):
    """The most a tool can do. Passive tools only read; active ones send requests the target did
    not expect; intrusive ones can change data or disturb the service; destructive ones can
    destroy data or take the service down and are off unless a pentest turns them on."""

    PASSIVE = "passive"
    ACTIVE = "active"
    INTRUSIVE = "intrusive"
    DESTRUCTIVE = "destructive"


RISK_ORDER = (ToolRisk.PASSIVE, ToolRisk.ACTIVE, ToolRisk.INTRUSIVE, ToolRisk.DESTRUCTIVE)


class Tier(StrEnum):
    """Where a tool comes from: Python inside the app, a program in the image, a pack image, an
    optional pull, or an administrator's own."""

    BUILTIN = "builtin"
    CORE = "core"
    PACK = "pack"
    OPTIONAL = "optional"
    CUSTOM = "custom"


class Capability(StrEnum):
    """The Linux capabilities a tool may be given. Everything else is always dropped."""

    NET_RAW = "NET_RAW"
    NET_ADMIN = "NET_ADMIN"
    NET_BIND_SERVICE = "NET_BIND_SERVICE"


# A tool that starts another program from its own arguments makes every value a command.
SHELLS = frozenset(
    {
        *("sh", "bash", "dash", "zsh", "ksh", "csh", "tcsh", "fish", "ash", "busybox"),
        *("env", "xargs", "sudo", "su", "doas", "nsenter", "chroot", "setpriv", "nohup"),
        *("timeout", "nice", "strace", "ltrace", "gdb", "find"),
    }
)
INTERPRETERS = re.compile(
    r"^(python[0-9.]*|perl[0-9.]*|ruby[0-9.]*|node|nodejs|php[0-9.]*|lua[0-9.]*|awk|gawk|mawk|sed|"
    r"tclsh|expect|pwsh|powershell|osascript|java|deno|bun)$"
)
CUSTOM_PREFIX = "x."


class When(Strict):
    """Arguments that are added only when a parameter is set (and, when `equals` is given, is
    that value)."""

    when: ParamName
    equals: str | int | bool | None = None
    args: list[Template] = Field(min_length=1, max_length=10)


class VersionProbe(Strict):
    """How to ask the tool which version it is: arguments to run, and a pattern whose first group
    is the version in the output."""

    args: list[Template] = Field(default_factory=lambda: ["--version"], max_length=5)
    pattern: Annotated[str, StringConstraints(max_length=200)] = r"([0-9]+(?:\.[0-9]+)+)"

    @model_validator(mode="after")
    def _pattern_has_a_group(self) -> Self:
        try:
            found = re.compile(self.pattern)
        except re.error:
            raise ValueError("the version pattern is not a valid regular expression") from None
        if found.groups != 1:
            raise ValueError("the version pattern needs exactly one group")
        return self


class Manifest(Strict):
    """One tool."""

    id: ToolId
    name: Title
    tier: Tier = Tier.CORE
    execution: Annotated[str, StringConstraints(pattern=r"^(process|builtin)$")] = "process"
    binary: Binary | None = None
    handler: Handler | None = None
    version: VersionProbe | None = None
    risk: ToolRisk
    capabilities: list[Capability] = Field(default_factory=list[Capability], max_length=3)
    params: dict[ParamName, Param] = Field(default_factory=dict, max_length=MAX_PARAMS)
    argv: list[Template | When] = Field(
        default_factory=list[Template | When], max_length=MAX_ARGUMENTS
    )
    timeout_s: int = Field(default=600, ge=1, le=86400)
    max_output_mb: int = Field(default=10, ge=1, le=512)
    parsers: list[ParserName] = Field(default_factory=list, max_length=8)
    image: Image | None = None
    homepage: Url | None = None
    explain: Text
    could_go_wrong: Text

    @model_validator(mode="after")
    def _is_sound(self) -> Self:
        problem = (
            self._kind_problem()
            or self._custom_problem()
            or _reference_problem(self)
            or self._capability_problem()
        )
        if problem:
            raise ValueError(problem)
        return self

    def _kind_problem(self) -> str | None:
        if self.execution == "builtin":
            if self.handler is None or self.binary or self.argv or self.image or self.version:
                return "a built-in tool has a handler and nothing else that runs a program"
            return None
        if self.binary is None or self.handler is not None:
            return "a tool that runs a program has a binary and no handler"
        if self.binary.rsplit("/", 1)[-1].lower() in SHELLS:
            return "a shell, or a program that starts other programs, cannot be a tool"
        return None

    def _custom_problem(self) -> str | None:
        if self.id.startswith(CUSTOM_PREFIX) != (self.tier is Tier.CUSTOM):
            return "only custom tools use ids that start with x."
        if self.tier is Tier.CUSTOM:
            name = (self.binary or "").rsplit("/", 1)[-1].lower()
            if self.execution != "process" or INTERPRETERS.match(name) or self.capabilities:
                return "a custom tool runs a program (not an interpreter) and has no capabilities"
        return None

    def _capability_problem(self) -> str | None:
        if len(set(self.capabilities)) != len(self.capabilities):
            return "each capability is listed once"
        return None

    def target_params(self) -> list[str]:
        """The parameters that name what to test. The scope guard checks every one of them."""
        return [name for name, param in self.params.items() if param.type is ParamType.TARGET]


def _templates(manifest: Manifest) -> Iterator[tuple[str, str | None, tuple[Piece, ...]]]:
    """Every template as (kind, the `when` parameter it sits under, its pieces)."""
    for item in manifest.argv:
        if isinstance(item, When):
            for text in item.args:
                yield "when", item.when, parse_template(text)
        else:
            yield "plain", None, parse_template(item)
    if manifest.version:
        for text in manifest.version.args:
            yield "version", None, parse_template(text)


def _use_problem(manifest: Manifest, owner: str | None, piece: Piece) -> str | None:
    param = manifest.params.get(piece.name or "")
    if param is None:
        return f"'{piece.name}' is used in an argument but is not a parameter"
    if param.type is ParamType.BOOLEAN:
        return f"'{piece.name}' is true or false, so it can only be used in a when"
    if param.many != piece.spread:
        return f"'{piece.name}' is a list, so write {{{piece.name}...}} (and only a list)"
    if not (param.required or param.default is not None or owner == piece.name):
        return f"'{piece.name}' may be missing, so it can only be used in its own when"
    return None


def _placeholder_problem(manifest: Manifest) -> tuple[set[str], str | None]:
    """The parameters the templates use, and the first problem with a placeholder."""
    used: set[str] = set()
    try:
        for kind, owner, pieces in _templates(manifest):
            for piece in (p for p in pieces if p.name is not None):
                used.add(piece.name or "")
                if kind == "version":
                    return used, "the version check cannot use parameters"
                if problem := _use_problem(manifest, owner, piece):
                    return used, problem
    except ValueError as error:
        return used, str(error)
    return used, None


def _reference_problem(manifest: Manifest) -> str | None:
    """Every placeholder names a parameter that will have a value, and every parameter is used."""
    used, problem = _placeholder_problem(manifest)
    if problem:
        return problem
    for item in manifest.argv:
        if isinstance(item, When):
            used.add(item.when)
            problem = _when_problem(manifest, item)
            if problem:
                return problem
    if manifest.execution == "process" and (unused := set(manifest.params) - used):
        return f"'{min(unused)}' is not used in any argument"
    return None


def _when_problem(manifest: Manifest, item: When) -> str | None:
    param = manifest.params.get(item.when)
    if param is None:
        return f"when '{item.when}': there is no such parameter"
    if (
        item.equals is not None
        and param.type is ParamType.ENUM
        and item.equals not in (param.values or [])
    ):
        return f"when '{item.when}': '{item.equals}' is not one of its values"
    if item.equals is not None and param.many:
        return f"when '{item.when}': a list cannot be compared"
    return None
