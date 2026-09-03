from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from clawfedora.core_config import core_contract


def _policy(repo_root: Path) -> dict[str, Any]:
    return core_contract(repo_root, "budget_policy.yaml")


def _ledger_path(repo_root: Path, runtime_root: Path) -> Path:
    ledger = _policy(repo_root).get("ledger", {})
    if not isinstance(ledger, dict):
        raise ValueError("finops: ledger invalide")
    relative = str(ledger.get("relative_path", ""))
    if not relative:
        raise ValueError("finops: relative_path absent")
    return runtime_root / relative


def append_cost_event(
    repo_root: Path,
    runtime_root: Path,
    *,
    event: str,
    amount_eur: float,
    reason: str,
    provider: str,
    project_id: str | None = None,
) -> dict[str, Any]:
    policy = _policy(repo_root)
    cloud = policy.get("cloud", {})
    if not isinstance(cloud, dict):
        raise ValueError("finops: politique cloud invalide")
    if cloud.get("enabled_by_default") is not False:
        raise ValueError("finops: cloud doit rester désactivé par défaut")
    if amount_eur < 0:
        raise ValueError("finops: montant négatif interdit")
    if not reason.strip():
        raise ValueError("finops: raison obligatoire")
    if not provider.strip():
        raise ValueError("finops: provider obligatoire")
    if event not in {"reservation", "charge", "release", "refund"}:
        raise ValueError(f"finops: événement inconnu: {event}")
    payload: dict[str, Any] = {
        "id": uuid4().hex,
        "at": datetime.now(UTC).isoformat(),
        "event": event,
        "amount_eur": round(float(amount_eur), 6),
        "provider": provider.strip(),
        "reason": reason.strip(),
    }
    if project_id:
        payload["project_id"] = project_id
    path = _ledger_path(repo_root, runtime_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    return payload


def summarize(repo_root: Path, runtime_root: Path) -> dict[str, Any]:
    path = _ledger_path(repo_root, runtime_root)
    if not path.exists():
        return {"events": 0, "charges_eur": 0.0, "reservations_eur": 0.0, "refunds_eur": 0.0}
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    charges = sum(float(row.get("amount_eur", 0)) for row in rows if row.get("event") == "charge")
    reservations = sum(
        float(row.get("amount_eur", 0)) for row in rows if row.get("event") == "reservation"
    )
    refunds = sum(float(row.get("amount_eur", 0)) for row in rows if row.get("event") == "refund")
    return {
        "events": len(rows),
        "charges_eur": round(charges, 6),
        "reservations_eur": round(reservations, 6),
        "refunds_eur": round(refunds, 6),
    }
