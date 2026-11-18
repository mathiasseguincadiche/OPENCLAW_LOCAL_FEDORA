"""Interpret imported infrastructure reports without trusting their execution claims."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

TOOLS = {"terraform", "ansible-lint", "docker", "kubeconform", "helm", "trivy", "smoke", "restore"}


def summarize(data: dict[str, Any]) -> dict[str, Any]:
    content, kind = data.get("content"), data.get("format")
    if not isinstance(content, str) or not 0 < len(content.encode()) <= 12000:
        raise ValueError("rapport limité à 12000 octets requis")
    value = json.loads(content)
    if not isinstance(value, dict):
        raise ValueError("rapport JSON objet requis")
    if kind == "trivy-image":
        digest = data.get("image_digest")
        metadata = value.get("Metadata", {})
        manifests = metadata.get("RepoDigests") if isinstance(metadata, dict) else None
        if (not isinstance(digest, str) or not re.fullmatch(r"sha256:[a-f0-9]{64}", digest)
                or not isinstance(manifests, list) or not any(
                    isinstance(m, str) and m.endswith("@" + digest) for m in manifests)):
            raise ValueError("digest de manifeste absent ou différent")
        results = value.get("Results")
        if not isinstance(results, list) or any(not isinstance(r, dict) for r in results):
            raise ValueError("résultats Trivy invalides")
        counts: dict[str, int] = {}
        for result in results:
            vulnerabilities = result.get("Vulnerabilities", [])
            if not isinstance(vulnerabilities, list):
                raise ValueError("liste de vulnérabilités invalide")
            for finding in vulnerabilities:
                severity = finding.get("Severity") if isinstance(finding, dict) else None
                if severity not in ("LOW", "MEDIUM", "HIGH", "CRITICAL", "UNKNOWN"):
                    raise ValueError("sévérité Trivy invalide")
                counts[severity] = counts.get(severity, 0) + 1
        return {"origin": "imported-report", "verification": "UNVERIFIED", "image_digest": digest,
                "vulnerabilities_by_severity": counts, "runtime_tested": False,
                "input_sha256": hashlib.sha256(content.encode()).hexdigest(),
                "scope": "vulnérabilités déclarées de l’image; autres scanners non évalués"}
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
