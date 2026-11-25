"""Synthetic positive/negative smoke cases for the operator's local validator image."""

from __future__ import annotations

import argparse
import io
import json
import subprocess
import tempfile
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any

from clawfedora.devops_lab import LabRefusal, image_is_pinned, run_lab

# No real project, credentials, provider downloads or service deployments.
CASES: dict[str, tuple[str, str, str]] = {
    "terraform-fmt": (
        "main.tf", 'output "ready" {\n  value = "yes"\n}\n',
        'output "ready" {\nvalue="yes"\n}\n',
    ),
    "terraform-validate": (
        "main.tf", 'output "ready" {\n  value = "yes"\n}\n',
        'output "ready" {\n  value = local.missing\n}\n',
    ),
    "ansible-lint": (
        "playbook.yml",
        "---\n- name: Synthetic fixture\n  hosts: localhost\n  gather_facts: false\n"
        "  tasks:\n    - name: Display marker\n      ansible.builtin.debug:\n"
        "        msg: ready\n",
        "---\n- name: Synthetic fixture\n  hosts: localhost\n  gather_facts: false\n"
        "  tasks:\n    - name: Invalid module\n      example.invalid.module:\n"
        "        msg: ready\n",
    ),
    "actionlint": (
        ".github/workflows/fixture.yml",
        "name: Fixture\non: workflow_dispatch\njobs:\n  test:\n"
        "    runs-on: ubuntu-latest\n    steps:\n      - run: echo ready\n",
        "name: Fixture\non: workflow_dispatch\njobs:\n  test:\n"
        "    runs-on: ubuntu-latest\n    steps:\n      - run: echo ${{ missing.value }}\n",
    ),
    "shellcheck": (
        "fixture.sh", '#!/bin/sh\nname="ready"\nprintf "%s\\n" "$name"\n',
        '#!/bin/sh\nname="ready"\nprintf "%s\\n" $name\n',
    ),
    "hadolint": (
        "Dockerfile", 'FROM scratch\nLABEL description="fixture"\n',
        "FROM scratch\nRUN apt-get update\n",
    ),
    "kubeconform": (
        "k8s/configmap.yaml",
        'apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: fixture\ndata:\n  ready: "yes"\n',
        "apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: fixture\ndata:\n  ready: true\n",
    ),
    "pytest": (
        "tests/test_fixture.py",
        "def test_marker():\n    assert 2 + 2 == 4\n",
        "def test_marker():\n    assert 2 + 2 == 5\n",
    ),
}


def qualify(image: str | None, *, apply: bool) -> dict[str, Any]:
    if apply and (not image or not image_is_pinned(image)):
        raise LabRefusal("Image locale immuable requise")
    rows: list[dict[str, Any]] = []
    for tool, (name, good, bad) in CASES.items():
        for case, content in (("positive", good), ("negative", bad)):
            row: dict[str, Any] = {
                "tool": tool, "case": case, "file": name,
                "expected": "zero" if case == "positive" else "nonzero",
                "status": "NOT_RUN",
            }
            rows.append(row)
            if not apply:
                continue
            with tempfile.TemporaryDirectory(prefix="clawfedora-validator-fixture-") as scratch:
                root = Path(scratch)
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
                output = io.StringIO()
                try:
                    with redirect_stdout(output):
                        code = run_lab(root, tool, image, apply=True)
                    row["exit_code"] = code
                    if code in {124, 125, 126, 127} or code < 0:
                        row["status"] = "EXECUTION_ERROR"
                    elif case == "positive":
                        row["status"] = "EXPECTED_EXIT" if code == 0 else "UNEXPECTED_EXIT"
                    else:
                        row["status"] = (
                            "REVIEW_NEGATIVE_LOG" if code != 0 else "UNEXPECTED_EXIT"
                        )
                except (ValueError, OSError, subprocess.SubprocessError) as exc:
                    row["status"] = "EXECUTION_ERROR"
                    row["reason"] = str(exc)[:500]
                row["log"] = output.getvalue()[-7000:]
    unexpected = any(row["status"] in {"EXECUTION_ERROR", "UNEXPECTED_EXIT"} for row in rows)
    return {
        "status": (
            "PLAN_ONLY" if not apply else
            "SMOKE_FAILED" if unexpected else "SMOKE_REVIEW_REQUIRED"
        ),
        "image": image, "cases": rows, "qualified": False, "approved": False,
        "note": "Relire chaque échec attendu et qualifier providers, collections et schémas réels.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = qualify(args.image, apply=args.apply)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1 if report["status"] == "SMOKE_FAILED" else 0
    except ValueError as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
