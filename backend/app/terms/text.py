"""The terms of use.

The text is data, written here once. The app shows it to each person before they can use it, and
`DISCLAIMER.md` at the root of the repository is rendered from the same sections (a test fails
when the two differ, and says how to write the file again). The version is a fingerprint of the
text, so changing a word asks everybody to accept again, and nothing can change without that.

This is not legal advice. The authors recommend that a lawyer reads the text before anybody relies
on it.
"""

import hashlib
import json

from pydantic import BaseModel, ConfigDict


class Section(BaseModel):
    """One part of the terms: a heading and its paragraphs."""

    model_config = ConfigDict(frozen=True)

    id: str
    title: str
    paragraphs: tuple[str, ...]


TITLE = "Terms of use"

SECTIONS: tuple[Section, ...] = (
    Section(
        id="permission",
        title="Test only what you are allowed to test",
        paragraphs=(
            "Blindspot sends real attacks at the targets you give it. Running it against a system "
            "without the owner's clear permission can be a crime in your country and in theirs.",
            "You may only point Blindspot at systems that you own, or where the owner has given "
            "you written permission that covers the target, the kinds of testing and the dates. "
            "Keep that permission. Blindspot asks you to confirm it before any pentest can start, "
            "and keeps a record of who confirmed it and when.",
        ),
    ),
    Section(
        id="responsibility",
        title="You are responsible for what you run",
        paragraphs=(
            "You decide what is in scope, what may be tried and when. Blindspot's scope checks "
            "and limits are safeguards, not a promise that nothing outside your intention can "
            "happen, and they do not replace your own care.",
            "Testing can disturb or damage a system, change or delete its data, send mail, lock "
            "accounts and cost money. Use a test environment where you can, take backups first, "
            "and tell the people who run the target before you begin.",
        ),
    ),
    Section(
        id="agents",
        title="AI agents make mistakes",
        paragraphs=(
            "Blindspot uses AI models to plan and carry out tests. They can misread a page, "
            "invent a result, miss a weakness or choose a step you did not expect. Check every "
            "finding before you rely on it or report it, and watch a running pentest.",
            "Text from the models you connect, and from the targets you test, may be sent to the "
            "AI providers you configure. Do not test systems whose data you may not share with "
            "those providers.",
        ),
    ),
    Section(
        id="liability",
        title="No warranty and no liability",
        paragraphs=(
            "Blindspot is provided as it is, without any warranty, express or implied, including "
            "any warranty of fitness for a purpose, accuracy or that it will find every weakness "
            "or work without interruption.",
            "To the fullest extent the law allows, the authors and contributors are not liable "
            "for any loss or damage of any kind that comes from using Blindspot or from misusing "
            "it, including damage to a target, loss of data or service, legal action, and "
            "consequences of a result that was wrong or missing. You use it at your own risk.",
        ),
    ),
    Section(
        id="changes",
        title="When these terms change",
        paragraphs=(
            "If this text changes, everyone is asked to read and accept it again before they "
            "continue. Who accepted which version, and when, is kept in the audit log.",
        ),
    ),
)


def _canonical() -> str:
    return json.dumps(
        [TITLE, [section.model_dump() for section in SECTIONS]],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


# A fingerprint of the words, so a change to the text is a change of version.
VERSION = hashlib.sha256(_canonical().encode()).hexdigest()[:12]


def render_markdown() -> str:
    """The terms as the Markdown document kept at the root of the repository."""
    parts = [
        f"# {TITLE}",
        f"Version `{VERSION}`. This file is written from `backend/app/terms/text.py`; change the "
        "words there and run `make terms` to write it again.",
        "This is not legal advice. Have a lawyer read it before you rely on it.",
    ]
    for number, section in enumerate(SECTIONS, start=1):
        parts.append(f"## {number}. {section.title}")
        parts.extend(section.paragraphs)
    return "\n\n".join(parts) + "\n"
