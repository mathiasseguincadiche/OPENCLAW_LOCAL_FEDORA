"""Consolidated native acceptance: read-only prechecks, no automatic physical certification."""
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from http.client import HTTPConnection, HTTPException
from pathlib import Path
from typing import Any

from clawfedora.contracts import validate_repository
from clawfedora.fedora_acceptance import fixed_command
from clawfedora.hardware_gate import collect_hardware_gate
from clawfedora.lifecycle import collect_health
from clawfedora.storage import load_settings, require_storage

SCHEMA = 1
PAGES = {
    "projects": "/",
    "discussions": "/discussions.html",
    "github": "/github.html",
    "notion": "/notion.html",
    "performance": "/performance.html",
}
SERVICES = (
    ("gateway", ["--user"], "openclaw-gateway.service"),
    ("atelier", ["--user"], "clawfedora-dashboard.service"),
    ("local-models", [], "ollama.service"),
)
HEALTH_IDS = (
    "repository-contracts", "runtime-root", "openclaw-cli", "ollama",
    "openclaw-gateway", "agent-workspaces", "openclaw-version", "ollama-version",
    "model-inventory", "selinux-enforcing", "firewalld", "b580-vulkan",
    "effective-inference-limits",
)
# Fixed GET destinations; no redirects, proxy settings or arbitrary body returned.
OLLAMA_READS = {
    "http://127.0.0.1:11434/api/version": "/api/version",
    "http://127.0.0.1:11434/api/tags": "/api/tags",
}
# The instructions are a plan, never executed by this command.
STAGES = (
    ("live-usb", "HUMAN", "LIVE_USB_FEDORA45_PREQUALIFICATION.md",
     "ISO officielle, observations matérielles et limites du Live USB"),
    ("installation", "EXPLICIT", "INSTALLATION_SIMPLE_FEDORA45.md",
     "Précheck, installation volontaire, stockage et session graphique"),
    ("short-inference", "EXPLICIT", "INSTALLATION_SIMPLE_FEDORA45.md",
     "quick-check : réponses locales des deux modèles et VRAM observée"),
    ("seven-roles", "HUMAN", "RECETTE_GLOBALE.md",
     "Sept rôles, routage attendu, outils et qualité des réponses"),
    ("project-lifecycle", "HUMAN", "RECETTE_GLOBALE.md",
     "Projet synthétique, validations humaines, exécution et preuve des livrables"),
    ("long-context", "HUMAN", "PERFORMANCE_PROJETS_LONGS.md",
     "Historique, reprise de projet, décisions et citations"),
    ("ornith-work-loop", "HUMAN", "RECETTE_GLOBALE.md",
     "Correction et tests réels dans le laboratoire isolé"),
    ("stream-recovery", "HUMAN", "STREAMING_DISCUSSIONS_NATIVES.md",
     "Premier fragment, arrêt effectif, verrou, reprise sans replay, retour arrière"),
    ("native-downloads", "HUMAN", "TELECHARGEMENTS_DISCUSSIONS.md",
     "PDF/DOCX/ODT, code, Draw.io/SVG, SHA-256 et isolation des fils"),
    ("github-notion", "HUMAN", "RECETTE_GLOBALE.md",
     "Lecture réelle, autorisation explicite de toute écriture sur ressources de test"),
    ("retrieval-vision", "HUMAN", "VISION_LOCALE_CANARY.md",
     "Citations et exactitude sur sources synthétiques, activation vision explicite"),
    ("backup-restore", "EXPLICIT", "RECETTE_GLOBALE.md",
     "Archive privée puis restauration isolée, reprise des fils et fichiers"),
    ("gpu-comparison", "EXPLICIT", "PROFILS_GPU_EXPERIMENTAUX.md",
     "Qwen et Ornith, 8K/16K/32K, profils comparés et retour à la référence"),
    ("native-visual", "HUMAN", "validation/VISUAL_RECEPTION_NATIVE.md",
     "Inspection réelle des pages et documents, captures sans secrets"),
    ("host-stability", "HUMAN", "RECETTE_GLOBALE.md",
     "Redémarrage, veille, AV1, stabilité et revue finale"),
)


def _ollama_read(url: str) -> dict[str, Any]:
    if url not in OLLAMA_READS:
        raise ValueError("Destination de réception non autorisée")
    client = HTTPConnection("127.0.0.1", 11434, timeout=5)
    try:
        client.request("GET", OLLAMA_READS[url])
        response = client.getresponse()
        if response.status != 200:
            raise ValueError("Inventaire local indisponible")
        raw = response.read(1_048_577)
        if len(raw) > 1_048_576:
            raise ValueError("Inventaire local trop volumineux")
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("Inventaire local invalide")
        return data
    except HTTPException as exc:
        raise ValueError("Inventaire local interrompu") from exc
    finally:
        client.close()


def _page(path: str) -> bool:
    if path not in PAGES.values():
        raise ValueError("Page de réception non autorisée")
    client = HTTPConnection("127.0.0.1", 18890, timeout=5)
    try:
        client.request("GET", path)
        response = client.getresponse()
        return response.status == 200 and response.getheader(
            "Content-Type", "",
        ).split(";", 1)[0].strip() == "text/html"
    except (OSError, HTTPException):
        return False
    finally:
        client.close()


def _row(identifier: str, status: str) -> dict[str, str]:
    return {"id": identifier, "status": status}


def _base(mode: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA,
        "mode": mode,
        "observed_at_utc": datetime.now(UTC).isoformat(),
        "verdict": "NOT_END_TO_END_QUALIFIED",
        "hardware_certified": False,
        "active_tests_executed": False,
        "remote_integrations_tested": False,
        "checks": [],
        "outstanding": [
            {"id": name, "kind": kind, "guide": guide, "expected_evidence": proof,
             "status": "NOT_RUN"}
            for name, kind, guide, proof in STAGES
        ],
    }


def campaign(
    repo: Path, *, mode: str = "plan", runtime: Path | None = None,
) -> dict[str, Any]:
    if mode not in {"plan", "source", "inspect"} or (mode == "inspect") != (runtime is not None):
        raise ValueError("Mode de réception invalide")
    report = _base(mode)
    report["precheck"] = "NOT_RUN"
    if mode == "plan":
        return report
    checks: list[dict[str, str]] = report["checks"]
    try:
        source = validate_repository(repo)
        checks.append(_row("source-contracts", "PASS" if source.ok else "FAIL"))
    except (OSError, ValueError, KeyError, TypeError):
        checks.append(_row("source-contracts", "FAIL"))
    if checks[-1]["status"] != "PASS":
        report["precheck"] = "BLOCKED"
        return report
    if mode == "source":
        report["precheck"] = "SOURCE_CONTRACTS_PASS"
        return report
    assert runtime is not None
    try:
        if not runtime.is_absolute() or any(
            path.is_symlink() for path in (runtime, *runtime.parents)
        ):
            raise ValueError("runtime non canonique")
        require_storage(runtime, load_settings(repo))
        marker = runtime / ".openclaw-fedora-runtime"
        if marker.is_symlink() or not marker.is_file():
            raise ValueError("runtime non géré")
    except (OSError, ValueError, KeyError, TypeError):
        checks.append(_row("managed-secondary-storage", "FAIL"))
        report["precheck"] = "BLOCKED"
        return report
    checks.append(_row("managed-secondary-storage", "PASS"))

    try:
        hardware = collect_hardware_gate(repo, "system")
        status = "FAIL" if not hardware.ok or not hardware.checks else (
            "REVIEW" if hardware.warnings else "PASS"
        )
    except (OSError, ValueError, KeyError, TypeError):
        status = "FAIL"
    checks.append(_row("system-gate", status))
    # Never retain command stdout, environment values, URLs from responses,
    # paths, model digests, project content or private connector data.
    try:
        health = collect_health(repo, runtime, probe=False, ollama_request=_ollama_read)
        for name in HEALTH_IDS:
            states = [item.status for item in health.checks if item.id == name]
            checks.append(_row(
                name, "PASS" if states and all(state == "PASS" for state in states) else "FAIL",
            ))
    except (OSError, ValueError, KeyError, TypeError):
        checks.extend(_row(name, "FAIL") for name in HEALTH_IDS)
    for name, flags, unit in SERVICES:
        for action in ("is-active", "is-enabled"):
            ok = fixed_command(["systemctl", *flags, action, "--quiet", unit])
            checks.append(_row(f"{name}-{action}", "PASS" if ok else "FAIL"))
    for name, path in PAGES.items():
        checks.append(_row(f"page-{name}", "PASS" if _page(path) else "FAIL"))
    report["precheck"] = (
        "READY_FOR_MANUAL_TESTS" if all(row["status"] == "PASS" for row in checks)
        else "REVIEW_REQUIRED"
    )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Recette globale native, sans inférence")
    parser.add_argument("--root", type=Path, required=True)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--source", action="store_true")
    group.add_argument("--inspect", action="store_true")
    parser.add_argument("--runtime-root", type=Path)
    args = parser.parse_args(argv)
    mode = "inspect" if args.inspect else "source" if args.source else "plan"
    if args.inspect != (args.runtime_root is not None):
        parser.error("--runtime-root est requis et réservé à --inspect")
    report = campaign(args.root, mode=mode, runtime=args.runtime_root)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["precheck"] in {
        "NOT_RUN", "SOURCE_CONTRACTS_PASS", "READY_FOR_MANUAL_TESTS",
    } else 1


if __name__ == "__main__":
    raise SystemExit(main())
