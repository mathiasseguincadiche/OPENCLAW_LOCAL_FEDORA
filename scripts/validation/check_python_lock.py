"""Validate a reviewed Python production constraint snapshot, without fetching packages.

The constraints make production deps exact; only wheel hashes can additionally
prove downloaded bytes. This tool intentionally distinguishes those guarantees.
"""
from __future__ import annotations

import argparse
import importlib.metadata as metadata
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LINE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9_.-]*)==([A-Za-z0-9][A-Za-z0-9_.+!-]*)$")


def canonical(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def constraints(path: Path) -> dict[str, str]:
    if not path.is_file() or path.is_symlink():
        raise ValueError("fichier de contraintes absent ou lié")
    entries: dict[str, str] = {}
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = LINE.fullmatch(line)
        if match is None:
            raise ValueError(f"contrainte non exacte à la ligne {number}")
        key = canonical(match.group(1))
        if key in entries:
            raise ValueError(f"contrainte dupliquée à la ligne {number}")
        entries[key] = match.group(2)
    if not entries:
        raise ValueError("contrainte vide")
    return entries


def verify(repo_root: Path, *, strict: bool = False) -> dict[str, object]:
    lock = constraints(repo_root / "config/python-runtime-constraints.txt")
    project = tomllib.loads((repo_root / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = project["project"]["dependencies"]
    required = {canonical(re.split(r"[<>=!~\[ ;]", spec, maxsplit=1)[0]) for spec in dependencies}
    missing = sorted(required - set(lock))
    if missing:
        raise ValueError("dépendances directes absentes du lock: " + ", ".join(missing))
    installed = {
        canonical(str(dist.metadata["Name"])): dist.version
        for dist in metadata.distributions()
        if dist.metadata.get("Name")
    }
    absent = sorted(set(lock) - set(installed))
    mismatches = sorted(
        key for key, value in lock.items()
        if key in installed and installed[key] != value
    )
    if absent or mismatches:
        raise ValueError(
            "environnement Python hors verrou (absent="
            + ",".join(absent) + "; versions=" + ",".join(mismatches) + ")"
        )
    # CI installs into a clean environment. Site-specific runtimes may have
    # separately audited dev/speech packages: this stricter check is CI-only.
    extras = sorted(set(installed) - set(lock) - {
        canonical(str(project["project"]["name"])), "pip", "setuptools", "wheel",
    })
    if strict and extras:
        raise ValueError("packages Python non verrouillés: " + ", ".join(extras))
    return {"verdict": "PYTHON_RUNTIME_CONSTRAINTS_PASS",
            "locked_packages": len(lock),
            "scope": "production-python-versions-not-wheel-hashes",
            "extra_packages": len(extras),
            "strict": strict}


def main() -> int:
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.root, strict=args.strict), sort_keys=True))
        return 0
    except (ValueError, OSError, KeyError, tomllib.TOMLDecodeError) as exc:
        print(json.dumps({"verdict": "PYTHON_RUNTIME_CONSTRAINTS_FAIL",
                          "reason": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
