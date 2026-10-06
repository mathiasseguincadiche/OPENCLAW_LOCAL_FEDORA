"""Interpret imported infrastructure reports without trusting their execution claims."""

from __future__ import annotations

import hashlib
import json
from typing import Any

TOOLS = {"terraform", "ansible-lint", "docker", "kubeconform", "helm", "trivy", "smoke", "restore"}


def summarize(data: dict[str, Any]) -> dict[str, Any]:
    content, kind = data.get("content"), data.get("format")
    if not isinstance(content, str) or not 0 < len(content.encode()) <= 12000:
        raise ValueError("rapport limité à 12000 octets requis")
    value = json.loads(content)
    if kind == "terraform-validate":
        if not isinstance(value, dict) or type(value.get("valid")) is not bool:
            raise ValueError("rapport terraform validate JSON requis")
        diagnostics = value.get("diagnostics", [])
        if not isinstance(diagnostics, list):
            raise ValueError("diagnostics Terraform invalides")
        checks = [
            {
                "tool": "terraform",
                "reported_status": "PASS" if value["valid"] else "FAIL",
                "finding_count": len(diagnostics),
            }
        ]
    elif kind == "ci-checks":
        if not isinstance(value, dict) or not isinstance(value.get("checks"), list):
            raise ValueError("objet checks requis")
        if not 1 <= len(value["checks"]) <= 20:
            raise ValueError("1 à 20 contrôles maximum")
        checks = []
        for check in value["checks"]:
            if (
                not isinstance(check, dict)
                or check.get("tool") not in TOOLS
                or type(check.get("exit_code")) is not int
            ):
                raise ValueError("outil infrastructure et exit_code entier requis")
            checks.append(
                {
                    "tool": check["tool"],
                    "reported_status": "PASS" if check["exit_code"] == 0 else "FAIL",
                    "exit_code": check["exit_code"],
                }
            )
    else:
        raise ValueError("format terraform-validate ou ci-checks requis")
    return {
        "origin": "imported-report",
        "verification": "UNVERIFIED",
        "checks": checks,
        "input_sha256": hashlib.sha256(content.encode()).hexdigest(),
        "runtime_tested": False,
        "skill_acquired": False,
        "scope": "rapport déclaré; vérifier provenance, commit et fichiers contrôlés; "
        "aucun outil exécuté, aucun secret ou journal brut retourné",
    }
