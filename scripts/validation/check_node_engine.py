"""Check that the active Node.js satisfies the pinned OpenClaw engine, before ``npm ci``.

Standard library only: it runs before the managed Python environment exists. Fedora 45's
default ``nodejs`` is Node 22, refused by OpenClaw; the installer uses ``nodejs24``. This
check turns npm's late EBADENGINE into an early, explained refusal.

Supported ranges are the comparator sets OpenClaw publishes (``>=24.16.0 <25 || >=26.1.0``);
anything else is refused rather than guessed. ``npm ci --engine-strict`` stays the authority.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOCK = ROOT / "config/npm-runtime/package-lock.json"
VERSION = re.compile(r"v?([0-9]+)\.([0-9]+)\.([0-9]+)")
COMPARATOR = re.compile(r"(>=|<=|>|<|=)?v?([0-9]+)(?:\.([0-9]+))?(?:\.([0-9]+))?")
FEDORA_HINT = (
    "Sur Fedora 45, installer Node 24 : sudo dnf install nodejs24 nodejs24-npm "
    "nodejs24-bin nodejs24-npm-bin, puis vérifier que `node --version` affiche v24."
)


def parse_version(text: str) -> tuple[int, int, int]:
    match = VERSION.fullmatch(text.strip())
    if match is None:
        raise ValueError(f"version Node illisible: {text.strip()[:40]}")
    return int(match[1]), int(match[2]), int(match[3])


def _comparator(version: tuple[int, int, int], token: str) -> bool:
    match = COMPARATOR.fullmatch(token)
    if match is None:
        raise ValueError(f"contrainte Node non prise en charge: {token}")
    operator = match[1] or "="
    bound = tuple(int(part) for part in match.groups()[1:] if part is not None)
    # A partial bound compares the same number of components: "<25" is "<25.0.0",
    # ">24" is ">=25.0.0" and "=24" is any 24.x, as npm's semver does.
    head = version[: len(bound)]
    return {
        "=": head == bound, ">=": head >= bound, ">": head > bound,
        "<": head < bound, "<=": head <= bound,
    }[operator]


def satisfies(version: tuple[int, int, int], expression: str) -> bool:
    alternatives = [part.strip() for part in expression.split("||")]
    if not expression.strip() or any(not part for part in alternatives):
        raise ValueError("contrainte Node vide")
    results = []
    for alternative in alternatives:
        # npm also accepts ">= 24.16.0": glue an operator to the version that follows.
        tokens = re.sub(r"(>=|<=|>|<|=)\s+", r"\1", alternative).split()
        # Evaluate every token (no short-circuit): an unsupported one is always refused.
        checks = [_comparator(version, token) for token in tokens]
        results.append(all(checks))
    return any(results)


def required_engine(lock_path: Path = LOCK) -> tuple[str, str]:
    package = json.loads(lock_path.read_text(encoding="utf-8"))["packages"]["node_modules/openclaw"]
    engine = package.get("engines", {}).get("node")
    if not isinstance(engine, str):
        raise ValueError("contrainte Node d'OpenClaw absente du verrou")
    return str(package["version"]), engine


def active_node_version() -> str:
    node = shutil.which("node")
    if node is None:
        raise ValueError("commande node introuvable. " + FEDORA_HINT)
    completed = subprocess.run(
        [node, "--version"], capture_output=True, text=True, timeout=20, check=False
    )
    if completed.returncode != 0:
        raise ValueError("node --version a échoué. " + FEDORA_HINT)
    return completed.stdout.strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node-version", help="version à tester au lieu de `node --version`")
    parser.add_argument("--lock", type=Path, default=LOCK)
    args = parser.parse_args(argv)
    try:
        openclaw, engine = required_engine(args.lock)
        text = args.node_version or active_node_version()
        if not satisfies(parse_version(text), engine):
            print(
                f"NODE_ENGINE_RESULT=REFUSED node={text} openclaw={openclaw} requis={engine!r}. "
                + FEDORA_HINT
            )
            return 2
    except (OSError, ValueError, KeyError, json.JSONDecodeError, subprocess.SubprocessError) as exc:
        print(f"NODE_ENGINE_RESULT=REFUSED {exc}")
        return 2
    print(f"NODE_ENGINE_RESULT=PASS node={text} openclaw={openclaw} requis={engine!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
