"""Monthly budget of the cloud route: reserve before every call, settle after, never undercount.

The user's real limit is 25 euros actually paid per month. Three independent layers hold it:
prepaid credits (the real purchase ceiling), the key limit at the provider, and this ledger.
The ledger counts in euros with a pessimistic factor for exchange rate, credit-purchase fees and
VAT, and can be reconciled with what was really invoiced.

One call is two records: a reservation of the worst-case cost written BEFORE the call, and a
settlement written after it. Whatever is uncertain keeps its worst-case estimate: a call
interrupted mid-way, a reservation never settled (crash), an answer with no usage. Only a call
the provider refused outright is released.
"""

from __future__ import annotations

import fcntl
import json
import os
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from clawfedora.cloud_state import CLOUD_STATE
from clawfedora.core_config import core_contract


class BudgetRefused(Exception):
    """The budget refuses the call: nothing is sent."""


@dataclass(frozen=True)
class Summary:
    month: str
    calls_ok: int
    calls_failed: int
    calls_uncertain: int
    pending: int
    spent_usd: float
    spent_eur: float
    billed_eur: float
    effective_eur: float
    cap_eur: float

    @property
    def remaining_eur(self) -> float:
        return max(0.0, self.cap_eur - self.effective_eur)

    @property
    def ratio(self) -> float:
        return self.effective_eur / self.cap_eur

    def level(self, alert_ratio: float) -> str:
        if self.ratio >= 1:
            return "exhausted"
        return "warning" if self.ratio >= alert_ratio else "ok"


def month_key(moment: float) -> str:
    return time.strftime("%Y-%m", time.gmtime(moment))


class Ledger:
    """BudgetGuard backed by an append-only monthly JSON-lines journal (mode 0600)."""

    def __init__(
        self,
        runtime: Path,
        policy: dict[str, Any],
        clock: Callable[[], float] = time.time,
    ) -> None:
        budget = policy["budget"]
        pricing = policy["model"]["pricing_usd_per_million"]
        self.runtime = runtime
        self.cap_eur = float(budget["monthly_cap_eur"])
        self.alert_ratio = float(budget["alert_ratio"])
        self.eur_per_usd = float(budget["eur_per_usd"])
        self._template = str(budget["ledger_file"])
        self._price_in = float(pricing["input"])
        self._price_out = float(pricing["output"])
        self._clock = clock
        self._threads = threading.Lock()

    # -- files --------------------------------------------------------------------
    def path(self, month: str) -> Path:
        return self.runtime / "state" / self._template.format(month=month)

    @contextmanager
    def _locked(self) -> Iterator[None]:
        directory = self.runtime / CLOUD_STATE
        directory.mkdir(parents=True, exist_ok=True)
        with self._threads:
            fd = os.open(directory / "ledger.lock", os.O_RDWR | os.O_CREAT, 0o600)
            with os.fdopen(fd, "w") as handle:
                fcntl.flock(handle, fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(handle, fcntl.LOCK_UN)

    def _append(self, month: str, record: dict[str, Any]) -> None:
        path = self.path(month)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    # -- accounting ---------------------------------------------------------------
    def _records(self, month: str) -> list[dict[str, Any]]:
        try:
            raw = self.path(month).read_text(encoding="utf-8")
        except FileNotFoundError:
            return []
        lines = raw.split("\n")
        # A write cut short by a crash leaves a last line without newline: the call it
        # announced never started, so it is ignored. Any other unreadable line is refused.
        truncated = bool(lines[-1])
        records: list[dict[str, Any]] = []
        for number, line in enumerate(lines, start=1):
            if not line:
                continue
            try:
                value = json.loads(line)
            except ValueError:
                if truncated and number == len(lines):
                    continue
                raise BudgetRefused(
                    f"journal du budget illisible (ligne {number}): réparer ou rapprocher avant "
                    "tout appel cloud"
                ) from None
            if isinstance(value, dict):
                records.append(value)
        return records

    def summary(self, month: str | None = None) -> Summary:
        month = month or month_key(self._clock())
        estimates: dict[str, float] = {}
        settled: dict[str, dict[str, Any]] = {}
        billed_eur = 0.0
        for record in self._records(month):
            kind = record.get("k")
            if kind == "reserve":
                estimates[str(record["id"])] = float(record["est_usd"])
            elif kind == "settle":
                settled[str(record["id"])] = record
            elif kind == "invoice":
                billed_eur = float(record["eur"])
        ok = failed = uncertain = pending = 0
        spent = 0.0
        for call_id, estimate in estimates.items():
            closing = settled.get(call_id)
            if closing is None:
                pending += 1
                spent += estimate
            elif closing["status"] == "failed":
                failed += 1
            elif closing["status"] == "ok" and closing.get("usd") is not None:
                ok += 1
                spent += float(closing["usd"])
            else:
                uncertain += 1
                spent += estimate
        spent_eur = spent * self.eur_per_usd
        return Summary(
            month=month, calls_ok=ok, calls_failed=failed, calls_uncertain=uncertain,
            pending=pending, spent_usd=spent, spent_eur=spent_eur, billed_eur=billed_eur,
            effective_eur=max(spent_eur, billed_eur), cap_eur=self.cap_eur,
        )

    def estimate_usd(self, input_tokens: int, max_output_tokens: int) -> float:
        """Worst case of one call: the whole input, and an output of the maximum length."""
        return (input_tokens * self._price_in + max_output_tokens * self._price_out) / 1_000_000

    def _actual_usd(self, usage: dict[str, Any] | None) -> float | None:
        if not usage:
            return None
        cost = usage.get("cost")
        if isinstance(cost, int | float) and not isinstance(cost, bool) and cost >= 0:
            return float(cost)
        prompt, completion = usage.get("prompt_tokens"), usage.get("completion_tokens")
        if isinstance(prompt, int) and isinstance(completion, int):
            return (prompt * self._price_in + completion * self._price_out) / 1_000_000
        return None

    # -- BudgetGuard --------------------------------------------------------------
    def reserve(self, *, input_tokens: int, max_output_tokens: int) -> _Reservation:
        estimate = self.estimate_usd(input_tokens, max_output_tokens)
        month = month_key(self._clock())
        with self._locked():
            current = self.summary(month)
            projected = current.effective_eur + estimate * self.eur_per_usd
            if projected > self.cap_eur:
                worst = estimate * self.eur_per_usd
                raise BudgetRefused(
                    f"plafond mensuel atteint: {current.effective_eur:.2f} € sur "
                    f"{self.cap_eur:.0f} € ce mois-ci ; un appel de {worst:.2f} € au pire "
                    "est refusé"
                )
            call_id = uuid.uuid4().hex[:16]
            self._append(
                month,
                {"k": "reserve", "id": call_id, "at": _stamp(self._clock()), "month": month,
                 "est_usd": round(estimate, 8), "input_tokens": input_tokens,
                 "max_output_tokens": max_output_tokens},
            )
        return _Reservation(self, call_id, month, estimate)

    def _settle(
        self, call_id: str, month: str, estimate: float, usage: dict[str, Any] | None, status: str
    ) -> None:
        usd = self._actual_usd(usage) if status == "ok" else None
        record: dict[str, Any] = {
            "k": "settle", "id": call_id, "at": _stamp(self._clock()), "month": month,
            "status": status, "usd": None if usd is None else round(usd, 8),
        }
        if usd is not None and usd > estimate:
            record["overrun"] = True
        if isinstance(usage, dict):
            record["tokens"] = {
                key: usage[key]
                for key in ("prompt_tokens", "completion_tokens", "total_tokens")
                if isinstance(usage.get(key), int)
            }
        with self._locked():
            self._append(month, record)

    def record_invoice(self, eur: float, month: str | None = None, note: str = "") -> None:
        """What was really paid this month, from the provider's statement (cap includes it)."""
        if not 0 <= eur <= 1000:
            raise ValueError("montant facturé invalide")
        month = month or month_key(self._clock())
        with self._locked():
            self._append(month, {"k": "invoice", "at": _stamp(self._clock()), "month": month,
                                 "eur": round(eur, 2), "note": note[:200]})


class _Reservation:
    def __init__(self, ledger: Ledger, call_id: str, month: str, estimate: float) -> None:
        self._ledger, self._id, self._month, self._estimate = ledger, call_id, month, estimate
        self._done = False

    def settle(self, usage: dict[str, Any] | None, status: str) -> None:
        if self._done:
            return
        self._done = True
        self._ledger._settle(self._id, self._month, self._estimate, usage, status)


def _stamp(moment: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(moment))


def load_ledger(
    runtime: Path, repo_root: Path, clock: Callable[[], float] = time.time
) -> Ledger:
    return Ledger(runtime, core_contract(repo_root, "cloud_policy.yaml"), clock)
