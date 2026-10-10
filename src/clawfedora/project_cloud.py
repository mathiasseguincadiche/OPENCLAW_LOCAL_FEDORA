"""Cloud in the project workshop: per-project consent, visible pause, model and cost shown.

The cloud is never a default of the workshop. A project goes through it only after an explicit
approval of that project, bound to the exact sources it had at that moment. When a cloud step
cannot run (filter block, budget, provider, gateway, changed sources), the work PAUSES and says
why. It is never silently redone locally: continuing locally is a separate decision, taken by
revoking the approval.
"""

from __future__ import annotations

import json
import os
import re
import time
from contextlib import suppress
from pathlib import Path
from typing import Any

from clawfedora.cloud_budget import BudgetRefused, load_ledger
from clawfedora.cloud_privacy import LABELS
from clawfedora.cloud_state import cloud_status, recent_events
from clawfedora.project_common import (
    assert_no_symlinks,
    now,
    read_json,
    sha256_file,
    validate_project_id,
    write_json,
)
from clawfedora.project_control import cloud_pause_path

PROJECT_CLOUD = "state/project-cloud"
CONSENT_TEXT = (
    "Ce projet enverra au cloud (DeepSeek V4.1 Flash via OpenRouter, par la passerelle locale) ses "
    "consignes, les extraits de sources lus par les agents et les résultats d'outils, après "
    "filtrage des secrets. Le filtre reconnaît les identifiants, mots de passe et clés ; il ne "
    "reconnaît pas un contenu confidentiel qui n'en a pas l'allure (nom de serveur interne, "
    "configuration d'un employeur). N'approuvez que des sources qui peuvent quitter cet "
    "ordinateur. Le plafond mensuel de 25 € s'applique. Si un envoi est bloqué ou impossible, "
    "le projet se met en pause : il ne repasse jamais en local sans votre décision."
)
RUN_LOG_TAIL = 500
BUDGET_MESSAGE = (
    "le plafond mensuel du budget cloud est atteint. Attendre le mois prochain, ou retirer "
    "l'accord cloud pour poursuivre en local."
)


class CloudPause(RuntimeError):
    """A cloud step cannot run: the work stops and says why."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


# -- files --------------------------------------------------------------------------
def _project_id(project: Path) -> str:
    return validate_project_id(str(read_json(project / "project.json")["project_id"]))


def _directory(runtime: Path) -> Path:
    directory = runtime / PROJECT_CLOUD
    assert_no_symlinks(directory, label="état cloud des projets")
    return directory


def consent_path(runtime: Path, project: Path) -> Path:
    return _directory(runtime) / f"{_project_id(project)}.consent.json"


def _runs_path(runtime: Path, project: Path) -> Path:
    return _directory(runtime) / f"{_project_id(project)}.runs.jsonl"


def sources_digest(project: Path) -> str:
    """Fingerprint of every input file: an approval covers exactly these sources."""
    import hashlib

    digest = hashlib.sha256()
    for scope in ("intake", "sources"):
        root = project / scope
        if not root.is_dir():
            continue
        assert_no_symlinks(root, label=scope)
        for path in sorted(p for p in root.rglob("*") if p.is_file()):
            digest.update(f"{path.relative_to(project).as_posix()}:{sha256_file(path)}\n".encode())
    return digest.hexdigest()


# -- consent ------------------------------------------------------------------------
def grant(repo_root: Path, runtime: Path, project: Path, *, acknowledged: bool) -> dict[str, Any]:
    """Approve the cloud for this project. Requires the cloud to be verified and activated."""
    if acknowledged is not True:
        raise ValueError("accord explicite requis: lire et accepter le texte d'accord cloud")
    ready, reason = cloud_status(runtime, repo_root)
    if not ready:
        raise ValueError(f"cloud indisponible, accord impossible: {reason}")
    record = {
        "project_id": _project_id(project),
        "granted_at": now(),
        "sources_digest": sources_digest(project),
        "scope": "cloud-deepseek",
        "consent_text_sha256": _text_digest(),
    }
    path = consent_path(runtime, project)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, record)
    path.chmod(0o600)
    cloud_pause_path(runtime, project).unlink(missing_ok=True)
    return record


def revoke(runtime: Path, project: Path) -> bool:
    """Withdraw the approval: later steps of this project run locally. Returns True if one existed."""
    path = consent_path(runtime, project)
    existed = path.exists()
    path.unlink(missing_ok=True)
    cloud_pause_path(runtime, project).unlink(missing_ok=True)
    return existed


def _text_digest() -> str:
    import hashlib

    return hashlib.sha256(CONSENT_TEXT.encode()).hexdigest()


def consent_state(repo_root: Path, runtime: Path, project: Path) -> dict[str, Any]:
    """none (local), granted (cloud allowed now), stale (sources changed), inactive (cloud off)."""
    path = consent_path(runtime, project)
    if not path.is_file():
        return {"state": "none", "reason": "aucun accord cloud pour ce projet"}
    record = read_json(path)
    if record.get("sources_digest") != sources_digest(project):
        return {
            "state": "stale",
            "reason": "les sources du projet ont changé depuis l'accord: approuver à nouveau",
            "granted_at": record.get("granted_at"),
        }
    ready, reason = cloud_status(runtime, repo_root)
    if not ready:
        return {"state": "inactive", "reason": f"cloud indisponible: {reason}",
                "granted_at": record.get("granted_at")}
    return {"state": "granted", "reason": "cloud autorisé pour ce projet",
            "granted_at": record.get("granted_at")}


# -- pause --------------------------------------------------------------------------
def write_pause(runtime: Path, project: Path, code: str, message: str, task: str = "") -> None:
    path = cloud_pause_path(runtime, project)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, {"code": code, "message": message, "task": task, "at": now()})


def read_pause(runtime: Path, project: Path) -> dict[str, Any] | None:
    path = cloud_pause_path(runtime, project)
    if not path.is_file() or path.is_symlink():
        return None
    value = read_json(path)
    return value if isinstance(value, dict) else None


def classify_failure(events: list[dict[str, Any]]) -> tuple[str, str] | None:
    """Why a cloud step failed, read from the gateway log. None: the cloud answered."""
    decisions = [str(event.get("decision")) for event in events]
    blocked = [e for e in events if e.get("decision") == "blocked"]
    if blocked:
        kinds = sorted({str(c) for e in blocked for c in e.get("categories", [])})
        what = "; ".join(LABELS.get(kind, kind) for kind in kinds) or "contenu sensible"
        return "privacy_blocked", (
            f"le filtre de confidentialité a bloqué un envoi ({what}). Retirer ce contenu des "
            "sources, ou retirer l'accord cloud pour poursuivre en local."
        )
    if "budget_refused" in decisions:
        return "budget_refused", BUDGET_MESSAGE
    if "upstream_error" in decisions or "upstream_unreachable" in decisions or (
        "interrupted" in decisions
    ):
        return "provider_unavailable", (
            "le fournisseur cloud est indisponible ou a coupé la réponse. Réessayer plus tard, "
            "ou retirer l'accord cloud pour poursuivre en local."
        )
    if not decisions:
        return "gateway_unreachable", (
            "la passerelle cloud locale ne répond pas (service arrêté ?). Vérifier "
            "clawfedora-cloud-gateway, ou retirer l'accord cloud pour poursuivre en local."
        )
    return None


# -- runs ---------------------------------------------------------------------------
def _model_of(runtime: Path, session: str) -> tuple[str | None, str | None]:
    name = re.sub(r"[^A-Za-z0-9_.-]", "_", session)[:120] or "session"
    try:
        record = read_json(runtime / "state/model-runs" / f"{name}.json")
    except (OSError, ValueError):
        return None, None
    provider, model = record.get("provider"), record.get("model")
    return (str(provider) if provider else None, str(model) if model else None)


def _append_run(runtime: Path, project: Path, record: dict[str, Any]) -> None:
    path = _runs_path(runtime, project)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def runs(runtime: Path, project: Path) -> list[dict[str, Any]]:
    try:
        lines = _runs_path(runtime, project).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    result: list[dict[str, Any]] = []
    for line in lines[-RUN_LOG_TAIL:]:
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if isinstance(value, dict):
            result.append(value)
    return result


class ProjectRunner:
    """Routes each agent call of a project and records which model answered, at what cost.

    Without an approval it is transparent: the local runner is called exactly as before.
    """

    def __init__(self, repo_root: Path, runtime: Path, project: Path, base: Any) -> None:
        self.repo_root, self.runtime, self.project, self.base = repo_root, runtime, project, base
        self.task = ""

    def __call__(self, role: str, prompt: str, session: str) -> dict[str, Any]:
        state = consent_state(self.repo_root, self.runtime, self.project)
        if state["state"] == "none":
            response = self.base(role, prompt, session)
            self._log(role, session, "local", 0.0)
            return response  # type: ignore[no-any-return]
        if state["state"] != "granted":
            raise self._pause(
                "consent_stale" if state["state"] == "stale" else "cloud_inactive", state["reason"]
            )
        ledger = load_ledger(self.runtime, self.repo_root)
        try:
            before = ledger.summary()
        except BudgetRefused as exc:
            raise self._pause("budget_unreadable", str(exc)) from None
        if before.level(ledger.alert_ratio) == "exhausted":
            raise self._pause("budget_refused", BUDGET_MESSAGE)
        started = time.time()
        try:
            response = self.base(role, prompt, session, route="cloud")
        except Exception as exc:
            self._log(role, session, "cloud", self._spent(ledger, before.spent_eur), failed=True)
            failure = classify_failure(recent_events(self.runtime, started))
            if failure is not None:
                raise self._pause(failure[0], failure[1]) from exc
            raise
        cloud_pause_path(self.runtime, self.project).unlink(missing_ok=True)
        self._log(role, session, "cloud", self._spent(ledger, before.spent_eur))
        return response  # type: ignore[no-any-return]

    @staticmethod
    def _spent(ledger: Any, before_eur: float) -> float:
        try:
            return max(0.0, float(ledger.summary().spent_eur) - before_eur)
        except (BudgetRefused, OSError, ValueError):
            return 0.0

    def _pause(self, code: str, message: str) -> CloudPause:
        write_pause(self.runtime, self.project, code, message, self.task)
        return CloudPause(code, message)

    def _log(
        self, role: str, session: str, route: str, eur: float, *, failed: bool = False
    ) -> None:
        provider, model = _model_of(self.runtime, session)
        # The journal is a display aid; the budget ledger remains the accounting truth.
        with suppress(OSError):
            _append_run(
                self.runtime,
                self.project,
                {"at": now(), "task": self.task, "role": role, "session": session,
                 "route": route, "provider": provider, "model": model,
                 "eur": round(eur, 6), "failed": failed},
            )


def project_runner(
    repo_root: Path, runtime: Path, project: Path, *, plain_text: bool = False, base: Any = None
) -> ProjectRunner:
    if base is None:
        from clawfedora.project_worker import openclaw_runner

        base = openclaw_runner(runtime, repo_root, plain_text=plain_text)
    return ProjectRunner(repo_root, runtime, project, base)


# -- display ------------------------------------------------------------------------
def overview(repo_root: Path, runtime: Path) -> dict[str, Any]:
    """Cloud and month budget, for the top of the workshop."""
    ready, reason = cloud_status(runtime, repo_root)
    value: dict[str, Any] = {"ready": ready, "reason": reason}
    if not ready:
        return value
    try:
        ledger = load_ledger(runtime, repo_root)
        summary = ledger.summary()
        value["budget"] = {
            "month": summary.month,
            "spent_eur": round(summary.effective_eur, 2),
            "cap_eur": summary.cap_eur,
            "remaining_eur": round(summary.remaining_eur, 2),
            "level": summary.level(ledger.alert_ratio),
        }
    except (BudgetRefused, OSError, ValueError, KeyError) as exc:
        value["budget"] = {"error": str(exc)}
    return value


def view(repo_root: Path, runtime: Path, project: Path) -> dict[str, Any]:
    """What the workshop shows for one project: approval, pause, models and cost."""
    state = consent_state(repo_root, runtime, project)
    history = runs(runtime, project)
    models: dict[str, int] = {}
    for run in history:
        label = f"{run.get('route')} · {run.get('model') or 'modèle non relevé'}"
        models[label] = models.get(label, 0) + 1
    last = history[-1] if history else None
    return {
        "state": state["state"],
        "reason": state["reason"],
        "granted_at": state.get("granted_at"),
        "pause": read_pause(runtime, project),
        "calls_cloud": sum(1 for run in history if run.get("route") == "cloud"),
        "calls_local": sum(1 for run in history if run.get("route") == "local"),
        "cost_eur": round(sum(float(run.get("eur", 0.0)) for run in history), 6),
        "models": models,
        "last": {k: last.get(k) for k in ("route", "model", "task", "at", "failed")}
        if last
        else None,
        "consent_text": CONSENT_TEXT,
    }
