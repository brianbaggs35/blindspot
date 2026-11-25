"""The argument templates of a manifest: literal text with `{name}` placeholders.

`{name}` is replaced by the value of the parameter `name`, as part of one argument. `{name...}` as
a whole argument is replaced by one argument for each value of a list parameter. `{{` and `}}` are
a literal brace. Any other brace is a mistake and is refused when the manifest is loaded, so a
template can never mean something different from what it says.
"""

import re
from dataclasses import dataclass

_TOKEN = re.compile(r"\{\{|\}\}|\{([a-z][a-z0-9_]{0,31})(\.\.\.)?\}|[{}]")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
MAX_TEMPLATE = 300


@dataclass(frozen=True)
class Piece:
    """Either some literal text, or a placeholder (`name`, and whether it is spread)."""

    literal: str = ""
    name: str | None = None
    spread: bool = False


def parse_template(text: str) -> tuple[Piece, ...]:
    """The pieces of a template. Raises ValueError, with a message that can be shown, when it is
    not one a manifest may hold."""
    if len(text) > MAX_TEMPLATE or _CONTROL.search(text):
        raise ValueError("an argument is too long or has control characters")
    pieces: list[Piece] = []
    position = 0
    for match in _TOKEN.finditer(text):
        pieces.append(Piece(literal=text[position : match.start()]))
        position = match.end()
        if match.group(1) is not None:
            pieces.append(Piece(name=match.group(1), spread=match.group(2) is not None))
        elif match.group(0) in ("{{", "}}"):
            pieces.append(Piece(literal=match.group(0)[0]))
        else:
            raise ValueError(
                f"a brace in '{text}' is not part of a placeholder; write {{{{ or }}}}"
            )
    pieces.append(Piece(literal=text[position:]))
    kept = tuple(piece for piece in pieces if piece.name is not None or piece.literal)
    if any(piece.spread for piece in kept) and (len(kept) != 1):
        raise ValueError(f"'{text}' spreads a list, so it must be the whole argument")
    return kept


def starts_with_value(pieces: tuple[Piece, ...]) -> bool:
    """True when the argument begins with a placeholder, so a value could pose as an option."""
    return bool(pieces) and pieces[0].name is not None
