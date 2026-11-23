"""A small second methodology, written as a pack folder, for the tests."""

from pathlib import Path
from typing import Any

import yaml

METHODOLOGY: dict[str, Any] = {
    "id": "ptes",
    "name": "Penetration Testing Execution Standard",
    "version": "1.0",
    "source_url": "https://www.pentest-standard.org/",
    "license": "Public",
    "categories": [
        {
            "id": "PTES-RECON",
            "name": "Intelligence gathering",
            "tests": [
                {
                    "id": "PTES-RECON-01",
                    "name": "Passive reconnaissance",
                    "reference": "https://www.pentest-standard.org/index.php/Intelligence_Gathering",
                    "objectives": ["Learn what is public about the target"],
                    "tags": ["recon"],
                },
                {"id": "PTES-RECON-02", "name": "Active reconnaissance"},
            ],
        },
        {
            "id": "PTES-EXPL",
            "name": "Exploitation",
            "tests": [{"id": "PTES-EXPL-01", "name": "Exploit a confirmed weakness"}],
        },
    ],
}
TOOLS: dict[str, Any] = {
    "tests": {
        "PTES-RECON-01": {"tools": ["b.osint"], "risk": "safe"},
        "PTES-RECON-02": {"tools": ["c.nmap"], "risk": "active"},
        "PTES-EXPL-01": {"manual_review": True, "risk": "intrusive"},
    }
}
PLAYBOOK: dict[str, Any] = {
    "summary": "Collect public facts.",
    "instructions": "Use only public sources.",
    "tools": ["b.osint"],
    "evidence": ["The source of each fact"],
    "success": "Everything public was found.",
    "failure": "Something private is public.",
}


def write_pack(root: Path, **changes: object) -> Path:
    """Write the sample pack under `root`; `changes` replace whole files (a `None` removes one)."""
    folder = root / "ptes"
    (folder / "playbooks").mkdir(parents=True, exist_ok=True)
    files: dict[str, object] = {
        "methodology.yaml": METHODOLOGY,
        "tools.yaml": TOOLS,
        "playbooks/recon.yaml": {"PTES-RECON-01": PLAYBOOK},
        "reporting.yaml": {"categories": {"PTES-RECON": "Recon"}},
    } | changes
    for name, content in files.items():
        path = folder / name
        if content is None:
            path.unlink(missing_ok=True)
        else:
            path.write_text(content if isinstance(content, str) else yaml.safe_dump(content))
    return folder


def playbook(**changes: Any) -> dict[str, Any]:
    """The sample playbook with some fields replaced."""
    return PLAYBOOK | changes
