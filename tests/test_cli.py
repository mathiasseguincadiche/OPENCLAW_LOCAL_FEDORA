from __future__ import annotations

from pathlib import Path

from clawfedora.cli import main

ROOT = Path(__file__).resolve().parents[1]


def test_validate_cli_passes(capsys: object) -> None:
    assert main(["--root", str(ROOT), "validate"]) == 0


def test_audit_non_strict_is_portable() -> None:
    # CI n'est pas Fedora 44/B580: le mode non strict doit produire des WARN,
    # jamais fabriquer un faux FAIL matériel.
    assert main(["--root", str(ROOT), "audit", "--json"]) == 0
