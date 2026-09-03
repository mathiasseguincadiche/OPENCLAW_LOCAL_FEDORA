from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from clawfedora.core_config import core_contract

POSITIVE_EVENTS = {"reservation", "charge"}
NEGATIVE_EVENTS = {"release", "refund"}


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


def _rows(repo_root: Path, runtime_root: Path) -> list[dict[str, Any]]:
    path = _ledger_path(repo_root, runtime_root)
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError("finops: ligne ledger invalide")
        rows.append(value)
    return rows


def _signed_amount(row: dict[str, Any]) -> float:
    amount = float(row.get("amount_eur", 0.0))
    event = str(row.get("event", ""))
    if event in POSITIVE_EVENTS:
        return amount
    if event in NEGATIVE_EVENTS:
        return -amount
    return 0.0


def _within_period(row: dict[str, Any], now: datetime, period: str) -> bool:
    try:
        at = datetime.fromisoformat(str(row.get("at", "")))
    except ValueError:
        return False
    if at.tzinfo is None:
        at = at.replace(tzinfo=UTC)
    if period == "day":
        return at.astimezone(UTC).date() == now.date()
    if period == "month":
        utc = at.astimezone(UTC)
        return utc.year == now.year and utc.month == now.month
    raise ValueError(f"finops: période inconnue: {period}")


def _enforce_limits(
    repo_root: Path,
    runtime_root: Path,
    *,
    amount_eur: float,
    project_id: str | None,
    now: datetime,
) -> None:
    policy = _policy(repo_root)
    limits = policy.get("limits", {})
    behavior = policy.get("behavior", {})
    if not isinstance(limits, dict) or not isinstance(behavior, dict):
        raise ValueError("finops: limites/comportement invalides")
    if behavior.get("on_limit") != "deny" or behavior.get("allow_manual_override") is not False:
        raise ValueError("finops: politique de dépassement doit rester deny sans override")
    rows = _rows(repo_root, runtime_root)
    day_total = sum(_signed_amount(row) for row in rows if _within_period(row, now, "day"))
    month_total = sum(_signed_amount(row) for row in rows if _within_period(row, now, "month"))
    project_total = sum(
        _signed_amount(row)
        for row in rows
        if project_id is not None and row.get("project_id") == project_id
    )
    checks = (
        ("daily", day_total + amount_eur, float(limits.get("daily_eur", 0.0))),
        ("monthly", month_total + amount_eur, float(limits.get("monthly_eur", 0.0))),
    )
    for label, candidate, limit in checks:
        if limit <= 0 or candidate > limit + 1e-9:
            raise ValueError(f"finops: limite {label} dépassée ({candidate:.6f}>{limit:.6f})")
    if project_id is not None:
        limit = float(limits.get("per_project_eur", 0.0))
        candidate = project_total + amount_eur
        if limit <= 0 or candidate > limit + 1e-9:
            raise ValueError(
                f"finops: limite projet dépassée ({candidate:.6f}>{limit:.6f})"
            )


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
    behavior = policy.get("behavior", {})
    if policy.get("cloud_enabled_by_default") is not False:
        raise ValueError("finops: cloud doit rester désactivé par défaut")
    if not isinstance(behavior, dict) or behavior.get("require_reason") is not True:
        raise ValueError("finops: raison obligatoire par contrat")
    if amount_eur < 0:
        raise ValueError("finops: montant négatif interdit")
    if not reason.strip():
        raise ValueError("finops: raison obligatoire")
    if not provider.strip():
        raise ValueError("finops: provider obligatoire")
    if event not in POSITIVE_EVENTS | NEGATIVE_EVENTS:
        raise ValueError(f"finops: événement inconnu: {event}")
    now = datetime.now(UTC)
    if event in POSITIVE_EVENTS:
        _enforce_limits(
            repo_root,
            runtime_root,
            amount_eur=float(amount_eur),
            project_id=project_id,
            now=now,
        )
    payload: dict[str, Any] = {
        "id": uuid4().hex,
        "at": now.isoformat(),
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
    rows = _rows(repo_root, runtime_root)
    charges = sum(float(row.get("amount_eur", 0)) for row in rows if row.get("event") == "charge")
    reservations = sum(
        float(row.get("amount_eur", 0)) for row in rows if row.get("event") == "reservation"
    )
    refunds = sum(float(row.get("amount_eur", 0)) for row in rows if row.get("event") == "refund")
    releases = sum(float(row.get("amount_eur", 0)) for row in rows if row.get("event") == "release")
    return {
        "events": len(rows),
        "charges_eur": round(charges, 6),
        "reservations_eur": round(reservations, 6),
        "refunds_eur": round(refunds, 6),
        "releases_eur": round(releases, 6),
        "net_exposure_eur": round(sum(_signed_amount(row) for row in rows), 6),
    }
